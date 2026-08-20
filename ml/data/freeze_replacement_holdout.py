from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ml.data.adapters.base import file_sha256
from ml.data.schema import AceDatasetExample, DatasetLabels, DatasetSplit
from ml.data.select_fast_track import (
    DEFAULT_SEED,
    _representation_report,
    select_examples,
)

FREEZE_VERSION = "replacement-holdout-v1"
DEFAULT_HOLDOUT_SEED = DEFAULT_SEED + 1


def _hash_lines(values: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def _read(path: Path) -> list[AceDatasetExample]:
    with path.open() as source:
        return [
            AceDatasetExample.model_validate_json(line)
            for line in source
            if line.strip()
        ]


def freeze_holdout(
    source_path: Path,
    exclusion_path: Path,
    output_dir: Path,
    *,
    rows: int = 4_000,
    seed: int = DEFAULT_HOLDOUT_SEED,
    max_total_variation: float = 0.08,
) -> dict[str, Any]:
    source = _read(source_path)
    excluded = _read(exclusion_path)
    excluded_groups = {value.identity.group_id for value in excluded}
    excluded_ids = {value.identity.example_id for value in excluded}
    excluded_source_records = {value.provenance.source_record_id for value in excluded}

    source_group_splits: defaultdict[str, set[str]] = defaultdict(set)
    source_by_group: defaultdict[str, list[AceDatasetExample]] = defaultdict(list)
    for value in source:
        source_group_splits[value.identity.group_id].add(value.split.name)
        source_by_group[value.identity.group_id].append(value)
    if any(len(splits) != 1 for splits in source_group_splits.values()):
        raise ValueError("source dataset contains cross-split groups")

    eligible_groups = {
        group_id
        for group_id, values in source_by_group.items()
        if values[0].split.name == "train"
        and group_id not in excluded_groups
        and not any(
            value.identity.example_id in excluded_ids
            or value.identity.parent_example_id in excluded_ids
            or value.provenance.source_record_id in excluded_source_records
            for value in values
        )
    }
    eligible = [
        value
        for group_id in sorted(eligible_groups)
        for value in source_by_group[group_id]
    ]
    if len(eligible) < rows:
        raise ValueError(
            f"only {len(eligible)} unused train rows remain for a {rows}-row holdout"
        )
    selected, selection = select_examples(
        eligible,
        train_rows=rows,
        seed=seed,
        max_total_variation=max_total_variation,
    )
    selected_groups = {value.identity.group_id for value in selected}
    selected_ids = {value.identity.example_id for value in selected}
    if selected_groups.intersection(excluded_groups) or selected_ids.intersection(
        excluded_ids
    ):
        raise AssertionError("replacement holdout overlaps the prior fast-track dataset")
    if any(
        value.identity.parent_example_id in excluded_ids
        or value.provenance.source_record_id in excluded_source_records
        for value in selected
    ):
        raise AssertionError("replacement holdout contains a related excluded record")

    blinded = []
    for value in selected:
        copy = value.model_copy(deep=True)
        copy.labels = DatasetLabels(label_source="unreviewed")
        copy.split = DatasetSplit(
            name="golden",
            grouping_keys=["identity.group_id"],
        )
        blinded.append(copy)
    blinded.sort(key=lambda value: value.identity.example_id)
    dataset_bytes = "".join(value.model_dump_json() + "\n" for value in blinded)
    pre_review_representation = _representation_report(eligible, selected)
    output_path = output_dir / "replacement-holdout.blinded.jsonl"
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "freeze_version": FREEZE_VERSION,
        "seed": seed,
        "source_dataset": str(source_path),
        "source_dataset_sha256": file_sha256(source_path),
        "source_rows": len(source),
        "exclusion_dataset": str(exclusion_path),
        "exclusion_dataset_sha256": file_sha256(exclusion_path),
        "excluded_rows": len(excluded),
        "excluded_groups": len(excluded_groups),
        "eligible_unused_train_rows": len(eligible),
        "eligible_unused_train_groups": len(eligible_groups),
        "row_count": len(blinded),
        "group_count": len(selected_groups),
        "split_counts": {"golden": len(blinded)},
        "label_policy": "all source labels stripped; independent review required",
        "label_source_counts": dict(
            sorted(Counter(value.labels.label_source for value in blinded).items())
        ),
        "source_pre_review_representation": pre_review_representation,
        "selection": selection,
        "selected_example_ids_sha256": _hash_lines(list(selected_ids)),
        "selected_group_ids_sha256": _hash_lines(list(selected_groups)),
        "selected_source_record_ids_sha256": _hash_lines(
            [value.provenance.source_record_id for value in selected]
        ),
        "prior_example_overlap": 0,
        "prior_group_overlap": 0,
        "prior_parent_overlap": 0,
        "prior_source_record_overlap": 0,
        "dataset": str(output_path),
        "dataset_sha256": hashlib.sha256(dataset_bytes.encode()).hexdigest(),
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if output_path.exists() or manifest_path.exists():
        if (
            output_path.is_file()
            and manifest_path.is_file()
            and output_path.read_text() == dataset_bytes
            and manifest_path.read_text() == manifest_bytes
        ):
            return {**manifest, "skipped": True}
        raise ValueError("replacement holdout is already frozen with different content")
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_dataset = output_path.with_suffix(".tmp")
    temporary_manifest = manifest_path.with_suffix(".tmp")
    temporary_dataset.write_text(dataset_bytes)
    temporary_manifest.write_text(manifest_bytes)
    temporary_dataset.replace(output_path)
    temporary_manifest.replace(manifest_path)
    return {**manifest, "skipped": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl"),
    )
    parser.add_argument(
        "--exclude",
        type=Path,
        default=Path("ml/data/generated/fast-track/option1/ace-fast-track.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ml/data/generated/fast-track/replacement-holdout"),
    )
    parser.add_argument("--rows", type=int, default=4_000)
    parser.add_argument("--seed", type=int, default=DEFAULT_HOLDOUT_SEED)
    parser.add_argument("--max-total-variation", type=float, default=0.08)
    args = parser.parse_args()
    print(
        json.dumps(
            freeze_holdout(
                args.source,
                args.exclude,
                args.output,
                rows=args.rows,
                seed=args.seed,
                max_total_variation=args.max_total_variation,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
