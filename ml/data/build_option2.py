from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from ml.data.adapters import (
    AmazonM2Adapter,
    Db1bAdapter,
    OnlineRetailAdapter,
    UsaSpendingAdapter,
)
from ml.data.adapters.base import file_sha256
from ml.data.schema import AceDatasetExample, DatasetLabels
from ml.data.transforms import (
    add_unrelated_item,
    assign_grouped_splits,
    cumulative_overspend,
    near_budget_match,
    remove_required_evidence,
)

DATASET_VERSION = "ace-public-benchmark-v2"
BUILD_SEED = 2026
SOURCE_PERCENTAGES = {
    "amazon-m2": 30,
    "uci-online-retail-ii": 17,
    "bts-db1b": 13,
    "usaspending-awards": 10,
}


def _hash(value: str) -> str:
    return hashlib.sha256(f"{BUILD_SEED}:{value}".encode()).hexdigest()


def _unique_groups(values: list[AceDatasetExample]) -> list[AceDatasetExample]:
    by_group: dict[str, AceDatasetExample] = {}
    for value in values:
        current = by_group.get(value.identity.group_id)
        if current is None or _hash(value.identity.example_id) < _hash(
            current.identity.example_id
        ):
            by_group[value.identity.group_id] = value
    return sorted(by_group.values(), key=lambda value: _hash(value.identity.example_id))


def construct_option2(
    source_values: dict[str, list[AceDatasetExample]],
    *,
    size: int = 150_000,
    review_count: int = 4_000,
) -> list[AceDatasetExample]:
    if size < 100 or size % 100:
        raise ValueError("Option 2 size must be at least 100 and divisible by 100")
    bases: list[AceDatasetExample] = []
    for source, percentage in SOURCE_PERCENTAGES.items():
        target = size * percentage // 100
        eligible = _unique_groups(source_values.get(source, []))
        if len(eligible) < target:
            raise ValueError(
                f"{source} requires {target} unique source groups, found {len(eligible)}"
            )
        bases.extend(eligible[:target])

    counter_count = size - len(bases)
    counter_parents = sorted(
        bases, key=lambda value: _hash(f"counter:{value.identity.example_id}")
    )[:counter_count]
    real_extras = [
        value.cart.line_items[0] for value in bases if value.context.domain == "retail"
    ]
    counterfactuals: list[AceDatasetExample] = []
    for index, parent in enumerate(counter_parents):
        transform = index % 4
        if transform == 0:
            child = near_budget_match(parent)
        elif transform == 1:
            child = cumulative_overspend(parent)
        elif transform == 2:
            child = remove_required_evidence(parent)
        else:
            extra = real_extras[index % len(real_extras)]
            child = add_unrelated_item(
                parent,
                product_id=extra.source_product_id or f"extra-{index}",
                description=extra.description,
                amount_minor=max(1, parent.cart.total_amount_minor // 20),
            )
            child.provenance.field_origins["cart.line_items.add_on"] = (
                "real_public_product"
            )
        counterfactuals.append(child)

    review_candidates = sorted(
        bases, key=lambda value: _hash(f"review:{value.identity.example_id}")
    )
    if review_count > len(review_candidates):
        raise ValueError("review count cannot exceed public base examples")
    review_ids = {
        value.identity.example_id for value in review_candidates[:review_count]
    }
    bases = [
        value.model_copy(update={"labels": DatasetLabels(label_source="unreviewed")})
        if value.identity.example_id in review_ids
        else value
        for value in bases
    ]
    values = [*bases, *counterfactuals]
    fixed_groups: dict[str, str] = {}
    ordered_reviews = sorted(
        (value for value in bases if value.identity.example_id in review_ids),
        key=lambda value: _hash(f"review-split:{value.identity.group_id}"),
    )
    review_splits = ["train"] * 7 + ["validation", "calibration", "golden"]
    for index, value in enumerate(ordered_reviews):
        fixed_groups[value.identity.group_id] = review_splits[index % 10]
    assigned = assign_grouped_splits(
        values,
        {
            "train": size * 70 // 100,
            "validation": size * 10 // 100,
            "calibration": size * 10 // 100,
            "golden": size * 10 // 100,
        },
        fixed_groups=fixed_groups,
        seed=BUILD_SEED,
    )
    return sorted(assigned, key=lambda value: value.identity.example_id)


def _load_source(source_dir: Path, adapter) -> list[AceDatasetExample]:
    return [
        value
        for record in adapter.iter_records(source_dir)
        for value in adapter.normalize(record)
    ]


def _record_sha256(source_lock: dict) -> str:
    value = source_lock.get("sha256")
    value = value.get("records") if isinstance(value, dict) else value
    if not value:
        raise ValueError("every Option 2 source lock requires a records SHA-256")
    return str(value)


def build(source_root: Path, output_dir: Path, size: int, review_count: int) -> dict:
    lock = json.loads((source_root / "source-lock.json").read_text())
    sources_lock = lock["sources"]
    adapters = {
        "amazon-m2": AmazonM2Adapter(
            sources_lock["amazon-m2"]["version"],
            _record_sha256(sources_lock["amazon-m2"]),
        ),
        "uci-online-retail-ii": OnlineRetailAdapter(
            sources_lock["uci-online-retail-ii"]["version"],
            _record_sha256(sources_lock["uci-online-retail-ii"]),
        ),
        "bts-db1b": Db1bAdapter(
            sources_lock["bts-db1b"]["version"],
            _record_sha256(sources_lock["bts-db1b"]),
        ),
        "usaspending-awards": UsaSpendingAdapter(
            sources_lock["usaspending-awards"]["version"],
            _record_sha256(sources_lock["usaspending-awards"]),
        ),
    }
    sources = {
        name: _load_source(source_root / name, adapter)
        for name, adapter in adapters.items()
    }
    values = construct_option2(sources, size=size, review_count=review_count)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ace-public-benchmark.jsonl"
    output_path.write_text("".join(value.model_dump_json() + "\n" for value in values))
    manifest = {
        "dataset_version": DATASET_VERSION,
        "schema_version": "2.0",
        "row_count": len(values),
        "review_queue_count": sum(
            value.labels.label_source == "unreviewed" for value in values
        ),
        "sources": dict(Counter(value.provenance.source_dataset for value in values)),
        "evidence_origins": dict(
            Counter(value.provenance.evidence_origin for value in values)
        ),
        "transformations": dict(
            Counter(value.provenance.transformation for value in values)
        ),
        "splits": dict(Counter(value.split.name for value in values)),
        "source_lock": lock,
        "dataset_sha256": file_sha256(output_path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("ml/data/raw/option2"))
    parser.add_argument(
        "--output", type=Path, default=Path("ml/data/generated/option2")
    )
    parser.add_argument("--size", type=int, default=150_000)
    parser.add_argument("--review-count", type=int, default=4_000)
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.source, args.output, args.size, args.review_count), indent=2
        )
    )


if __name__ == "__main__":
    main()
