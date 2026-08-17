from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from ml.data.adapters.base import file_sha256
from ml.data.adapters.esci import EsciAdapter
from ml.data.schema import AceDatasetExample, DatasetLabels
from ml.data.transforms import (
    add_unrelated_item,
    assign_grouped_splits,
    cumulative_overspend,
    near_budget_match,
    remove_required_evidence,
)

DATASET_VERSION = "ace-esci-en-hybrid-v3"
DATASET_FILENAME = "ace-esci-en-hybrid.jsonl"
BUILD_SEED = 2026


def _hash(value: str) -> str:
    return hashlib.sha256(f"{BUILD_SEED}:{value}".encode()).hexdigest()


def _component_counts(size: int) -> dict[str, int]:
    if size < 20 or size % 10:
        raise ValueError("Option 1 size must be at least 20 and divisible by 10")
    return {
        "single": size * 50 // 100,
        "composite": size * 20 // 100,
        "counterfactual": size * 20 // 100,
        "review": size * 10 // 100,
    }


def _split_counts(size: int) -> dict[str, int]:
    return {
        "train": size * 70 // 100,
        "validation": size * 10 // 100,
        "calibration": size * 10 // 100,
        "golden": size * 10 // 100,
    }


def _take_locale(
    candidates: list[AceDatasetExample],
    count: int,
    used_groups: set[str],
    locale: str,
) -> list[AceDatasetExample]:
    eligible = [
        value
        for value in candidates
        if value.context.locale == locale and value.identity.group_id not in used_groups
    ]
    eligible.sort(key=lambda value: _hash(value.identity.example_id))
    selected = eligible[:count]
    if len(selected) != count:
        raise ValueError(f"not enough unique {locale} ESCI query groups for target {count}")
    used_groups.update(value.identity.group_id for value in selected)
    return selected


def _review_fixed_groups(review: list[AceDatasetExample]) -> dict[str, str]:
    ordered = sorted(
        review, key=lambda value: _hash(f"review:{value.identity.group_id}")
    )
    counts = {
        "train": len(review) // 2,
        "validation": len(review) // 6,
        "calibration": len(review) // 6,
    }
    counts["golden"] = len(review) - sum(counts.values())
    fixed: dict[str, str] = {}
    cursor = 0
    for split in ("train", "validation", "calibration", "golden"):
        for value in ordered[cursor : cursor + counts[split]]:
            fixed[value.identity.group_id] = split
        cursor += counts[split]
    return fixed


def construct_option1(
    candidates: Iterable[AceDatasetExample],
    *,
    size: int = 60_000,
    locale: str = "en-US",
) -> list[AceDatasetExample]:
    counts = _component_counts(size)
    # Keep one deterministic product judgement per query group to make leakage control explicit.
    best_by_group: dict[str, AceDatasetExample] = {}
    for candidate in candidates:
        current = best_by_group.get(candidate.identity.group_id)
        if current is None or _hash(candidate.identity.example_id) < _hash(
            current.identity.example_id
        ):
            best_by_group[candidate.identity.group_id] = candidate
    pool = list(best_by_group.values())
    used_groups: set[str] = set()

    singles = _take_locale(pool, counts["single"], used_groups, locale)
    composite_parents = _take_locale(pool, counts["composite"], used_groups, locale)
    review = _take_locale(pool, counts["review"], used_groups, locale)
    review = [
        value.model_copy(update={"labels": DatasetLabels(label_source="unreviewed")})
        for value in review
    ]

    extras = sorted(
        singles, key=lambda value: _hash(f"extra:{value.identity.example_id}")
    )
    composites: list[AceDatasetExample] = []
    for index, parent in enumerate(composite_parents):
        extra = extras[index % len(extras)].cart.line_items[0]
        amount = max(1, parent.cart.total_amount_minor // 10)
        child = add_unrelated_item(
            parent,
            product_id=extra.source_product_id or f"extra_{index}",
            description=extra.description,
            amount_minor=amount,
        )
        child.provenance.field_origins["cart.line_items.add_on"] = (
            f"real_public_product:{extra.source_product_id or 'unknown'}"
        )
        composites.append(child)

    transforms = (near_budget_match, cumulative_overspend, remove_required_evidence)
    counterfactuals: list[AceDatasetExample] = []
    locale_parents = [value for value in singles if value.context.locale == locale]
    for index in range(counts["counterfactual"]):
        counterfactuals.append(
            transforms[index % len(transforms)](
                locale_parents[index % len(locale_parents)]
            )
        )
    values = [*singles, *composites, *counterfactuals, *review]
    if len({value.identity.example_id for value in values}) != len(values):
        raise ValueError("dataset construction produced duplicate example IDs")
    assigned = assign_grouped_splits(
        values,
        _split_counts(size),
        fixed_groups=_review_fixed_groups(review),
        seed=BUILD_SEED,
    )
    return sorted(assigned, key=lambda value: value.identity.example_id)


def write_dataset(
    values: list[AceDatasetExample], output_dir: Path, source_lock: dict
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / DATASET_FILENAME
    path.write_text("".join(value.model_dump_json() + "\n" for value in values))
    manifest = {
        "dataset_version": DATASET_VERSION,
        "schema_version": "2.0",
        "seed": BUILD_SEED,
        "row_count": len(values),
        "review_queue_count": sum(
            value.labels.label_source == "unreviewed" for value in values
        ),
        "components": {
            "source_single": len(values) * 50 // 100,
            "source_grounded_composite": len(values) * 20 // 100,
            "grounded_counterfactual": len(values) * 20 // 100,
            "human_review_queue": len(values) * 10 // 100,
        },
        "splits": dict(Counter(value.split.name for value in values)),
        "locales": dict(Counter(value.context.locale for value in values)),
        "evidence_origins": dict(
            Counter(value.provenance.evidence_origin for value in values)
        ),
        "labels": dict(
            Counter(value.labels.deviation or "UNREVIEWED" for value in values)
        ),
        "transformations": dict(
            Counter(value.provenance.transformation for value in values)
        ),
        "source_lock": source_lock,
        "dataset_sha256": file_sha256(path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def build(source_dir: Path, output_dir: Path, size: int, locale: str) -> dict:
    lock_path = source_dir / "source-lock.json"
    if not lock_path.exists():
        raise FileNotFoundError(
            "run python -m ml.data.acquire_esci before building Option 1"
        )
    source_lock = json.loads(lock_path.read_text())
    adapter = EsciAdapter(
        revision=source_lock["revision"], sha256=source_lock["sha256"]
    )
    candidates = (
        normalized
        for record in adapter.iter_records(source_dir)
        for normalized in adapter.normalize(record)
    )
    return write_dataset(
        construct_option1(candidates, size=size, locale=locale), output_dir, source_lock
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("ml/data/raw/esci"))
    parser.add_argument(
        "--output", type=Path, default=Path("ml/data/generated/option1-en")
    )
    parser.add_argument("--size", type=int, default=60_000)
    parser.add_argument("--locale", default="en-US")
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.size, args.locale), indent=2))


if __name__ == "__main__":
    main()
