from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ml.data.build_dataset_v3 import _assert_isolation, _relationship_keys, _v3_labels
from ml.data.build_dataset_v4 import _read, _review_labels, _sha256
from ml.data.schema import AceDatasetExample, DatasetSplit

DATASET_VERSION = "ace-development-v4-semantic-policy"
BUILD_SEED = 2031
DETERMINISTIC_CANDIDATE_ROWS = 1_000
REVIEW_ROLE_COUNTS = Counter({
    "train_fit": 700,
    "calibration": 200,
    "policy_tuning": 200,
    "candidate_selection": 400,
})


def _stable(value: str, namespace: str) -> str:
    return hashlib.sha256(f"{BUILD_SEED}:{namespace}:{value}".encode()).hexdigest()


def _split(value: AceDatasetExample, name: str) -> DatasetSplit:
    return DatasetSplit(
        name=name,
        grouping_keys=[value.identity.group_id, value.provenance.source_record_id],
    )


def build_dataset(
    v3_dataset_path: Path,
    stage_b_reviewed_path: Path,
    stage_b_pool_path: Path,
    output_path: Path,
    *,
    deterministic_candidate_rows: int = DETERMINISTIC_CANDIDATE_ROWS,
) -> dict[str, Any]:
    manifest_path = output_path.with_suffix(".manifest.json")
    if output_path.exists() or manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite immutable Stage B dataset: {output_path}")
    v3 = [value for value in _read(v3_dataset_path) if value.split.name != "candidate_selection"]
    reviewed = _read(stage_b_reviewed_path)
    pool = _read(stage_b_pool_path)
    if Counter(value.split.name for value in reviewed) != REVIEW_ROLE_COUNTS:
        raise ValueError("Stage B reviews do not match the frozen role contract")

    selected: list[AceDatasetExample] = list(v3)
    for value in reviewed:
        selected.append(value.model_copy(
            deep=True,
            update={"labels": _review_labels(value), "split": _split(value, value.split.name)},
        ))
    blocked = _relationship_keys(selected)
    deterministic: list[AceDatasetExample] = []
    for value in sorted(
        (item for item in pool if item.labels.label_source == "deterministic_counterfactual"),
        key=lambda item: _stable(item.identity.example_id, "candidate:deterministic"),
    ):
        parent = value.identity.parent_example_id or ""
        if (
            value.identity.example_id in blocked["example"]
            or value.identity.group_id in blocked["group"]
            or value.provenance.source_record_id in blocked["source"]
            or parent in blocked["example"]
        ):
            continue
        deterministic.append(value.model_copy(
            deep=True,
            update={
                "labels": _v3_labels(value, None).model_copy(update={"label_source": "deterministic_policy_v4"}),
                "split": _split(value, "candidate_selection"),
            },
        ))
        keys = _relationship_keys([value])
        for key, values in keys.items():
            blocked[key].update(values)
        if len(deterministic) == deterministic_candidate_rows:
            break
    if len(deterministic) != deterministic_candidate_rows:
        raise ValueError("insufficient fresh deterministic rows for Stage B candidate")
    selected.extend(deterministic)
    selected.sort(key=lambda value: value.identity.example_id)
    _assert_isolation(selected)
    roles = Counter(value.split.name for value in selected)
    expected = Counter({
        "train_fit": 4_700,
        "calibration": 1_200,
        "policy_tuning": 1_200,
        "candidate_selection": 1_400,
    })
    if deterministic_candidate_rows == DETERMINISTIC_CANDIDATE_ROWS and roles != expected:
        raise ValueError(f"Stage B role counts mismatch: {dict(roles)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x") as output:
        for value in selected:
            output.write(value.model_dump_json() + "\n")
    manifest = {
        "dataset_version": DATASET_VERSION,
        "rows": len(selected),
        "roles": dict(sorted(roles.items())),
        "candidate_rows": roles["candidate_selection"],
        "candidate_sources": dict(sorted(Counter(
            value.labels.label_source for value in selected if value.split.name == "candidate_selection"
        ).items())),
        "v3_candidate_rows_reused": 0,
        "stage_b_reviewed_candidate_rows": 400,
        "fresh_deterministic_candidate_rows": len(deterministic),
        "v3_dataset_sha256": _sha256(v3_dataset_path),
        "stage_b_reviewed_sha256": _sha256(stage_b_reviewed_path),
        "stage_b_pool_sha256": _sha256(stage_b_pool_path),
        "dataset_sha256": _sha256(output_path),
        "production_claim_eligible": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Stage B structured dataset")
    parser.add_argument("--v3-dataset", type=Path, required=True)
    parser.add_argument("--stage-b-reviewed", type=Path, required=True)
    parser.add_argument("--stage-b-pool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_dataset(args.v3_dataset, args.stage_b_reviewed, args.stage_b_pool, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
