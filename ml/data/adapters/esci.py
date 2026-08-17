from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ml.data.adapters.base import AdapterError, SourceAdapter, SourceManifest
from ml.data.schema import (
    AceDatasetExample,
    Context,
    DatasetCart,
    DatasetConstraint,
    DatasetLabels,
    DatasetLineItem,
    DatasetMandate,
    DeviationLabel,
    EvidenceOrigin,
    ExpectedTreatment,
    Identity,
    MandateOrigin,
    Provenance,
    SemanticAnnotation,
    SemanticLabel,
)
from ml.data.transforms.splits import assign_split

ESCI_SOURCE_URL = "https://github.com/amazon-science/esci-data"
ESCI_LICENSE = "Apache-2.0"
ESCI_FILES = {
    "examples": "shopping_queries_dataset_examples.parquet",
    "products": "shopping_queries_dataset_products.parquet",
    "sources": "shopping_queries_dataset_sources.csv",
}
ESCI_REQUIRED_COLUMNS = {
    "examples": [
        "example_id",
        "query",
        "query_id",
        "product_id",
        "product_locale",
        "esci_label",
        "large_version",
        "split",
    ],
    "products": [
        "product_id",
        "product_locale",
        "product_title",
        "product_description",
        "product_bullet_point",
        "product_brand",
        "product_color",
    ],
}


def _stable_integer(value: str) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest()[:12], 16)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _locale_money(locale: str, example_id: str) -> tuple[str, int, int, int]:
    if locale == "jp":
        currency, exponent, base, step = "JPY", 0, 5000, 250
    else:
        currency, exponent, base, step = "USD", 2, 5000, 250
    budget = base + (_stable_integer(example_id) % 181) * step
    amount = max(1, round(budget * 0.8))
    return currency, exponent, budget, amount


def _weak_labels(esci_label: str) -> DatasetLabels:
    mappings = {
        "E": (
            DeviationLabel.MATCH,
            ExpectedTreatment.APPROVE,
            [],
            SemanticLabel.ENTAILMENT,
        ),
        "S": (
            DeviationLabel.AMBIGUOUS,
            ExpectedTreatment.STEP_UP,
            ["POSSIBLE_SUBSTITUTION"],
            SemanticLabel.NEUTRAL,
        ),
        "C": (
            DeviationLabel.VIOLATION,
            ExpectedTreatment.HOLD,
            ["COMPLEMENT_NOT_REQUESTED"],
            SemanticLabel.CONTRADICTION,
        ),
        "I": (
            DeviationLabel.VIOLATION,
            ExpectedTreatment.HOLD,
            ["UNRELATED_ITEM"],
            SemanticLabel.CONTRADICTION,
        ),
    }
    try:
        deviation, treatment, violations, semantic = mappings[esci_label]
    except KeyError as exc:
        raise AdapterError(f"unsupported ESCI label: {esci_label}") from exc
    return DatasetLabels(
        deviation=deviation,
        semantic=[
            SemanticAnnotation(
                constraint_id="c_product_intent", label=semantic, confidence=0.7
            )
        ],
        violation_types=violations,
        expected_treatment=treatment,
        label_source="weak_esci_mapping",
    )


class EsciAdapter(SourceAdapter):
    def __init__(self, *, revision: str, sha256: dict[str, str] | None = None) -> None:
        if len(revision) < 20:
            raise ValueError("ESCI revision must be an immutable commit SHA")
        self.manifest = SourceManifest(
            dataset="amazon-esci",
            version=revision,
            source_url=ESCI_SOURCE_URL,
            license=ESCI_LICENSE,
            files=ESCI_FILES,
            required_columns=ESCI_REQUIRED_COLUMNS,
            sha256=sha256 or {},
        )

    def validate_source(self, source_dir: Path) -> None:
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise AdapterError("pyarrow is required to validate ESCI") from exc
        for name in ("examples", "products"):
            path = source_dir / self.manifest.files[name]
            if not path.exists():
                raise AdapterError(f"missing ESCI {name} file: {path}")
            columns = set(pq.ParquetFile(path).schema.names)
            missing = set(self.manifest.required_columns[name]) - columns
            if missing:
                raise AdapterError(f"ESCI {name} is missing columns: {sorted(missing)}")

    def iter_records(self, source_dir: Path) -> Iterator[dict[str, Any]]:
        """Yield joined records in bounded batches through DuckDB's Arrow reader."""
        try:
            import duckdb
        except ImportError as exc:
            raise AdapterError("duckdb is required for streaming ESCI joins") from exc
        self.validate_source(source_dir)
        examples = str(source_dir / self.manifest.files["examples"])
        products = str(source_dir / self.manifest.files["products"])
        connection = duckdb.connect()
        query = connection.execute(
            """
            SELECT e.example_id, e.query, e.query_id, e.product_id, e.product_locale,
                   e.esci_label, e.large_version, e.split AS source_split,
                   p.product_title, p.product_description, p.product_bullet_point,
                   p.product_brand, p.product_color
            FROM read_parquet(?) e
            JOIN read_parquet(?) p USING (product_id, product_locale)
            WHERE e.large_version = 1 AND e.product_locale IN ('us', 'jp')
            """,
            [examples, products],
        )
        reader = query.fetch_record_batch(rows_per_batch=10_000)
        try:
            for batch in reader:
                yield from batch.to_pylist()
        finally:
            connection.close()

    def normalize(self, record: dict[str, Any]) -> Iterable[AceDatasetExample]:
        locale = _text(record["product_locale"]).lower()
        if locale not in {"us", "jp"}:
            return []
        example_id = _text(record["example_id"])
        query_id = _text(record["query_id"])
        product_id = _text(record["product_id"])
        query = _text(record["query"])
        title = _text(record.get("product_title")) or "Product title unavailable"
        description = _text(record.get("product_description"))
        bullets = _text(record.get("product_bullet_point"))
        evidence_text = "\n".join(
            value for value in (title, description, bullets) if value
        )
        currency, exponent, budget, amount = _locale_money(locale, example_id)
        locale_name = "ja-JP" if locale == "jp" else "en-US"
        market = "JP" if locale == "jp" else "US"
        objective = f"Purchase {query}."
        normalized = AceDatasetExample(
            identity=Identity(
                example_id=f"ace_esci_{example_id}",
                group_id=f"esci_query_{query_id}",
            ),
            provenance=Provenance(
                source_dataset=self.manifest.dataset,
                source_version=self.manifest.version,
                source_record_id=example_id,
                source_url=self.manifest.source_url,
                source_license=self.manifest.license,
                evidence_origin=EvidenceOrigin.REAL_PUBLIC,
                mandate_origin=MandateOrigin.SOURCE_QUERY,
                source_sha256=self.manifest.sha256.get("examples"),
                field_origins={
                    "mandate.objective_text": "real_public_query",
                    "cart.line_items.description": "real_public_product",
                    "cart.total_amount_minor": "synthetic",
                    "mandate.total_budget": "synthetic",
                },
            ),
            context=Context(domain="retail", locale=locale_name, market=market),
            mandate=DatasetMandate(
                objective_text=objective,
                constraints=[
                    DatasetConstraint(
                        constraint_id="c_product_intent",
                        type="semantic_attribute",
                        operator="required",
                        value=query,
                        source_span=query,
                    ),
                    DatasetConstraint(
                        constraint_id="c_budget",
                        type="total_budget",
                        operator="lte",
                        amount_minor=budget,
                        currency=currency,
                        currency_exponent=exponent,
                        source_span="synthetic research budget",
                    ),
                ],
            ),
            cart=DatasetCart(
                cart_id=f"cart_esci_{example_id}",
                merchant_id="amazon_esci_public",
                merchant_category="RETAIL",
                evidence_source="PUBLIC_DATASET_ESCI",
                evidence_trust="trusted",
                evidence_sufficiency="sufficient",
                currency=currency,
                currency_exponent=exponent,
                total_amount_minor=amount,
                line_items=[
                    DatasetLineItem(
                        line_item_id=f"li_esci_{product_id}",
                        source_product_id=product_id,
                        description=title,
                        quantity=1,
                        amount_minor=amount,
                        attributes={
                            "brand": _text(record.get("product_brand")),
                            "color": _text(record.get("product_color")),
                        },
                        evidence_text=evidence_text,
                    )
                ],
            ),
            labels=_weak_labels(_text(record["esci_label"])),
        )
        return [assign_split(normalized)]
