from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ml.data.adapters.base import (
    AdapterError,
    SourceAdapter,
    SourceManifest,
    file_sha256,
)
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


def _minor(value: Any) -> int:
    return max(1, round(float(value) * 100))


def _id(prefix: str, *values: Any) -> str:
    digest = hashlib.sha256(":".join(map(str, values)).encode()).hexdigest()[:20]
    return f"{prefix}_{digest}"


class JsonlSourceAdapter(SourceAdapter):
    """Common streaming boundary after source-specific raw-to-JSONL extraction."""

    filename = "records.jsonl"

    def validate_source(self, source_dir: Path) -> None:
        path = source_dir / self.filename
        if not path.exists():
            raise AdapterError(f"missing normalized source file: {path}")
        expected = self.manifest.sha256.get("records")
        if expected and file_sha256(path) != expected:
            raise AdapterError(f"source checksum does not match lock: {path}")

    def iter_records(self, source_dir: Path) -> Iterator[dict[str, Any]]:
        self.validate_source(source_dir)
        with (source_dir / self.filename).open() as source:
            for number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AdapterError(f"invalid JSON at source line {number}") from exc

    def _base(
        self,
        *,
        example_id: str,
        group_id: str,
        source_record_id: str,
        domain: str,
        locale: str,
        market: str,
        objective: str,
        constraints: list[DatasetConstraint],
        merchant_id: str,
        merchant_category: str,
        currency: str,
        line_item: DatasetLineItem,
        label: DatasetLabels,
        mandate_origin: MandateOrigin = MandateOrigin.SYNTHETIC_TEMPLATE,
    ) -> AceDatasetExample:
        total = line_item.amount_minor * line_item.quantity
        return AceDatasetExample(
            identity=Identity(example_id=example_id, group_id=group_id),
            provenance=Provenance(
                source_dataset=self.manifest.dataset,
                source_version=self.manifest.version,
                source_record_id=source_record_id,
                source_url=self.manifest.source_url,
                source_license=self.manifest.license,
                evidence_origin=EvidenceOrigin.REAL_PUBLIC,
                mandate_origin=mandate_origin,
                source_sha256=self.manifest.sha256.get("records"),
                field_origins={
                    "cart": "real_public",
                    "mandate": (
                        "real_public_query"
                        if mandate_origin == MandateOrigin.SOURCE_QUERY
                        else "synthetic_from_public_record"
                    ),
                },
            ),
            context=Context(domain=domain, locale=locale, market=market),
            mandate=DatasetMandate(objective_text=objective, constraints=constraints),
            cart=DatasetCart(
                cart_id=f"cart_{example_id}",
                merchant_id=merchant_id,
                merchant_category=merchant_category,
                evidence_source=f"PUBLIC_DATASET_{self.manifest.dataset.upper()}",
                evidence_trust="trusted",
                evidence_sufficiency="sufficient",
                currency=currency,
                currency_exponent=2,
                total_amount_minor=total,
                line_items=[line_item],
            ),
            labels=label,
        )


class AmazonM2Adapter(JsonlSourceAdapter):
    def __init__(self, revision: str, sha256: str | None = None) -> None:
        self.manifest = SourceManifest(
            dataset="amazon-m2",
            version=revision,
            source_url=(
                "https://www.aicrowd.com/challenges/"
                "amazon-kdd-cup-23-multilingual-recommendation-challenge"
            ),
            license="Apache-2.0",
            files={"records": self.filename},
            required_columns={
                "records": [
                    "session_id",
                    "locale",
                    "previous_product_ids",
                    "previous_titles",
                    "next_product_id",
                    "next_title",
                ]
            },
            sha256={"records": sha256} if sha256 else {},
        )

    def normalize(self, record: dict[str, Any]) -> Iterable[AceDatasetExample]:
        locale = str(record["locale"]).upper()
        if locale != "UK":
            return
        previous_ids = [str(value) for value in record["previous_product_ids"]]
        previous_titles = [str(value).strip() for value in record["previous_titles"]]
        if not previous_ids or not previous_titles:
            raise AdapterError("Amazon-M2 session must include previous products and titles")
        product = str(record["next_product_id"])
        title = str(record["next_title"]).strip()
        if not title:
            raise AdapterError("Amazon-M2 next product title cannot be empty")
        amount = _minor(record.get("next_price") or 50)
        session_id = str(record["session_id"])
        example_id = _id("ace_m2", session_id, product)
        value = self._base(
            example_id=example_id,
            group_id=f"m2_session_{session_id}",
            source_record_id=f"{session_id}:{product}",
            domain="retail",
            locale="en-GB",
            market="GB",
            objective=(
                "Purchase a product consistent with this recent shopping session: "
                + "; ".join(previous_titles[-5:])
                + "."
            ),
            constraints=[
                DatasetConstraint(
                    constraint_id="c_session_intent",
                    type="semantic_attribute",
                    operator="required",
                    value="consistent with recent products: " + "; ".join(previous_titles[-5:]),
                ),
                DatasetConstraint(
                    constraint_id="c_budget",
                    type="total_budget",
                    operator="lte",
                    amount_minor=max(amount + 1, round(amount * 1.2)),
                    currency=str(record.get("currency", "GBP")),
                    currency_exponent=2,
                ),
            ],
            merchant_id="amazon_m2_public",
            merchant_category="RETAIL",
            currency=str(record.get("currency", "GBP")),
            line_item=DatasetLineItem(
                line_item_id=f"line_{product}",
                source_product_id=product,
                description=title,
                quantity=1,
                amount_minor=amount,
                evidence_text="\n".join(
                    filter(
                        None, [title, str(record.get("next_description", ""))]
                    )
                ),
            ),
            label=DatasetLabels(
                deviation=DeviationLabel.MATCH,
                semantic=[
                    SemanticAnnotation(
                        constraint_id="c_session_intent",
                        label=SemanticLabel.ENTAILMENT,
                        confidence=0.55,
                    )
                ],
                expected_treatment=ExpectedTreatment.APPROVE,
                label_source="weak_session_transition",
            ),
        )
        value.provenance.field_origins.update(
            {
                "session.previous_products": "real_public",
                "cart.line_items.next_product": "real_public_observed_transition",
                "mandate": "synthetic_from_public_session",
            }
        )
        yield value


class OnlineRetailAdapter(JsonlSourceAdapter):
    def __init__(self, version: str, sha256: str | None = None) -> None:
        self.manifest = SourceManifest(
            dataset="uci-online-retail-ii",
            version=version,
            source_url="https://archive.ics.uci.edu/dataset/502/online+retail+ii",
            license="CC-BY-4.0",
            files={"records": self.filename},
            required_columns={
                "records": [
                    "invoice",
                    "stock_code",
                    "description",
                    "quantity",
                    "unit_price",
                ]
            },
            sha256={"records": sha256} if sha256 else {},
        )

    def normalize(self, record: dict[str, Any]) -> Iterable[AceDatasetExample]:
        quantity, unit = int(record["quantity"]), float(record["unit_price"])
        if quantity <= 0 or unit <= 0:
            return
        amount, description = _minor(unit), str(record["description"]).strip()
        total = amount * quantity
        example_id = _id("ace_uci", record["invoice"], record["stock_code"])
        value = self._base(
            example_id=example_id,
            group_id=f"uci_invoice_{record['invoice']}",
            source_record_id=f"{record['invoice']}:{record['stock_code']}",
            domain="retail",
            locale="en-GB",
            market=str(record.get("country", "GB")),
            objective=f"Purchase {quantity} units of {description}.",
            constraints=[
                DatasetConstraint(
                    constraint_id="c_product_intent",
                    type="semantic_attribute",
                    operator="required",
                    value=description,
                ),
                DatasetConstraint(
                    constraint_id="c_budget",
                    type="total_budget",
                    operator="lte",
                    amount_minor=max(total + 1, round(total * 1.1)),
                    currency="GBP",
                    currency_exponent=2,
                ),
            ],
            merchant_id="uci_retailer_anonymized",
            merchant_category="RETAIL",
            currency="GBP",
            line_item=DatasetLineItem(
                line_item_id=f"line_{record['stock_code']}",
                source_product_id=str(record["stock_code"]),
                description=description,
                quantity=quantity,
                amount_minor=amount,
                evidence_text=description,
            ),
            label=DatasetLabels(
                deviation=DeviationLabel.MATCH,
                semantic=[
                    SemanticAnnotation(
                        constraint_id="c_product_intent",
                        label=SemanticLabel.ENTAILMENT,
                    )
                ],
                expected_treatment=ExpectedTreatment.APPROVE,
                label_source="deterministic_counterfactual",
            ),
        )
        yield value


class Db1bAdapter(JsonlSourceAdapter):
    def __init__(self, version: str, sha256: str | None = None) -> None:
        self.manifest = SourceManifest(
            dataset="bts-db1b",
            version=version,
            source_url="https://www.transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EFI",
            license="US-Government-Public-Domain",
            files={"records": self.filename},
            required_columns={
                "records": ["itinerary_id", "origin", "destination", "market_fare"]
            },
            sha256={"records": sha256} if sha256 else {},
        )

    def normalize(self, record: dict[str, Any]) -> Iterable[AceDatasetExample]:
        fare = _minor(record["market_fare"])
        origin, destination = str(record["origin"]), str(record["destination"])
        example_id = _id("ace_db1b", record["itinerary_id"])
        yield self._base(
            example_id=example_id,
            group_id=example_id,
            source_record_id=str(record["itinerary_id"]),
            domain="travel",
            locale="en-US",
            market="US",
            objective=f"Book air travel from {origin} to {destination}.",
            constraints=[
                DatasetConstraint(
                    constraint_id="c_route",
                    type="route",
                    operator="eq",
                    value={"origin": origin, "destination": destination},
                ),
                DatasetConstraint(
                    constraint_id="c_budget",
                    type="total_budget",
                    operator="lte",
                    amount_minor=max(fare + 1, round(fare * 1.15)),
                    currency="USD",
                    currency_exponent=2,
                ),
            ],
            merchant_id=str(record.get("carrier", "db1b_anonymized_carrier")),
            merchant_category="AIRLINE",
            currency="USD",
            line_item=DatasetLineItem(
                line_item_id=f"line_{example_id}",
                description=f"Air itinerary {origin} to {destination}",
                quantity=1,
                amount_minor=fare,
                attributes={"origin": origin, "destination": destination},
                evidence_text=f"Published itinerary from {origin} to {destination}",
            ),
            label=DatasetLabels(
                deviation=DeviationLabel.MATCH,
                expected_treatment=ExpectedTreatment.APPROVE,
                label_source="deterministic_counterfactual",
            ),
        )


class UsaSpendingAdapter(JsonlSourceAdapter):
    def __init__(self, version: str, sha256: str | None = None) -> None:
        self.manifest = SourceManifest(
            dataset="usaspending-awards",
            version=version,
            source_url="https://api.usaspending.gov/",
            license="US-Government-Public-Domain",
            files={"records": self.filename},
            required_columns={
                "records": ["award_id", "recipient", "description", "amount"]
            },
            sha256={"records": sha256} if sha256 else {},
        )

    def normalize(self, record: dict[str, Any]) -> Iterable[AceDatasetExample]:
        amount = _minor(record["amount"])
        recipient, description = str(record["recipient"]), str(record["description"])
        example_id = _id("ace_usaspending", record["award_id"])
        value = self._base(
            example_id=example_id,
            group_id=example_id,
            source_record_id=str(record["award_id"]),
            domain="procurement",
            locale="en-US",
            market="US",
            objective=f"Authorize procurement from {recipient} for {description}.",
            constraints=[
                DatasetConstraint(
                    constraint_id="c_merchant",
                    type="allowed_merchant",
                    operator="in",
                    value=[recipient],
                ),
                DatasetConstraint(
                    constraint_id="c_budget",
                    type="total_budget",
                    operator="lte",
                    amount_minor=max(amount + 1, round(amount * 1.05)),
                    currency="USD",
                    currency_exponent=2,
                ),
            ],
            merchant_id=recipient,
            merchant_category="PROCUREMENT",
            currency="USD",
            line_item=DatasetLineItem(
                line_item_id=f"line_{example_id}",
                description=description,
                quantity=1,
                amount_minor=amount,
                evidence_text=description,
            ),
            label=DatasetLabels(
                deviation=DeviationLabel.MATCH,
                expected_treatment=ExpectedTreatment.APPROVE,
                label_source="deterministic_counterfactual",
            ),
        )
        value.provenance.field_origins["cart.line_items.description"] = str(
            record.get("description_origin", "real_public")
        )
        yield value
