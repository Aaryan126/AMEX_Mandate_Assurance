from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ml.data.build_dataset_v3 import _relationship_keys
from ml.data.build_dataset_v4 import _read, _sha256
from ml.data.schema import AceDatasetExample, DatasetSplit

DATASET_VERSION = "ace-semantic-v4-replay"
BUILD_SEED = 2031
REPLAY_TARGET = 2_100
ROLE_COUNTS = {
    "stage_b_train": 700,
    "validation": 200,
    "calibration": 200,
    "stage_a_train": 200,
}


def _stable(value: str, namespace: str) -> str:
    return hashlib.sha256(f"{BUILD_SEED}:{namespace}:{value}".encode()).hexdigest()


def _semantic_label(value: AceDatasetExample) -> str:
    if len(value.labels.semantic) != 1:
        raise ValueError(f"{value.identity.example_id} must have exactly one semantic label")
    return value.labels.semantic[0].label.value


def _with_split(value: AceDatasetExample, split: str) -> AceDatasetExample:
    return value.model_copy(
        deep=True,
        update={
            "split": DatasetSplit(
                name=split,
                grouping_keys=[value.identity.group_id, value.provenance.source_record_id],
            )
        },
    )


def _select_replay(values: list[AceDatasetExample], count: int) -> list[AceDatasetExample]:
    candidates = [value for value in values if value.split.name == "train"]
    if count > len(candidates):
        raise ValueError(f"requested {count} replay rows from only {len(candidates)} train rows")
    label_counts = Counter(_semantic_label(value) for value in candidates)
    exact = {label: count * size / len(candidates) for label, size in label_counts.items()}
    targets = {label: int(number) for label, number in exact.items()}
    for label, _ in sorted(
        exact.items(), key=lambda item: (-(item[1] - targets[item[0]]), item[0])
    )[: count - sum(targets.values())]:
        targets[label] += 1
    selected: list[AceDatasetExample] = []
    for label, target in sorted(targets.items()):
        bucket = sorted(
            (value for value in candidates if _semantic_label(value) == label),
            key=lambda value: _stable(value.identity.example_id, f"replay:{label}"),
        )
        selected.extend(bucket[:target])
    return sorted(selected, key=lambda value: value.identity.example_id)


def _assert_relationship_isolation(values: list[AceDatasetExample]) -> None:
    roles: dict[str, str] = {}
    sources: dict[str, str] = {}
    for value in values:
        split = value.split.name
        prior_group = roles.setdefault(value.identity.group_id, split)
        prior_source = sources.setdefault(value.provenance.source_record_id, split)
        if prior_group != split or prior_source != split:
            raise ValueError("semantic-v4 relationship crosses train/validation/calibration")


def build_corpus(
    stage_b_reviewed_path: Path,
    stage_a_reviewed_path: Path,
    replay_source_path: Path,
    output_path: Path,
    *,
    replay_target: int = REPLAY_TARGET,
) -> dict[str, Any]:
    if output_path.exists() or output_path.with_suffix(".manifest.json").exists():
        raise FileExistsError(f"refusing to overwrite immutable semantic-v4 corpus: {output_path}")
    stage_b = _read(stage_b_reviewed_path)
    stage_a = _read(stage_a_reviewed_path)
    replay_source = _read(replay_source_path)
    stage_b_train = [value for value in stage_b if value.split.name == "train_fit"]
    validation = [value for value in stage_b if value.split.name == "policy_tuning"]
    calibration = [value for value in stage_b if value.split.name == "calibration"]
    stage_a_train = [value for value in stage_a if value.split.name == "train_fit"]
    actual_roles = {
        "stage_b_train": len(stage_b_train),
        "validation": len(validation),
        "calibration": len(calibration),
        "stage_a_train": len(stage_a_train),
    }
    if actual_roles != ROLE_COUNTS:
        raise ValueError("reviewed inputs do not satisfy the frozen semantic-v4 role contract")
    replay = _select_replay(replay_source, replay_target)
    output = [
        *(_with_split(value, "train") for value in stage_b_train),
        *(_with_split(value, "train") for value in stage_a_train),
        *(_with_split(value, "train") for value in replay),
        *(_with_split(value, "validation") for value in validation),
        *(_with_split(value, "calibration") for value in calibration),
    ]
    ids = [value.identity.example_id for value in output]
    if len(ids) != len(set(ids)):
        raise ValueError("semantic-v4 corpus contains duplicate example IDs")
    _assert_relationship_isolation(output)
    stage_b_keys = _relationship_keys(stage_b)
    candidate = [value for value in stage_b if value.split.name == "candidate_selection"]
    candidate_keys = _relationship_keys(candidate)
    selected_keys = _relationship_keys(output)
    if any(candidate_keys[key].intersection(selected_keys[key]) for key in candidate_keys):
        raise ValueError("Stage B candidate relationship entered semantic training")

    output.sort(key=lambda value: value.identity.example_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x") as destination:
        for value in output:
            destination.write(value.model_dump_json() + "\n")
    split_counts = Counter(value.split.name for value in output)
    manifest = {
        "dataset_version": DATASET_VERSION,
        "rows": len(output),
        "split_counts": dict(sorted(split_counts.items())),
        "training_sources": {
            "stage_b_new_reviewed": len(stage_b_train),
            "stage_a_train_reviewed": len(stage_a_train),
            "prior_train_replay": len(replay),
        },
        "semantic_labels": dict(sorted(Counter(_semantic_label(value) for value in output).items())),
        "semantic_labels_by_split": dict(sorted(Counter(f"{value.split.name}:{_semantic_label(value)}" for value in output).items())),
        "candidate_rows_excluded": len(candidate),
        "candidate_relationship_hashes": {
            key: hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()
            for key, values in candidate_keys.items()
        },
        "stage_b_reviewed_sha256": _sha256(stage_b_reviewed_path),
        "stage_a_reviewed_sha256": _sha256(stage_a_reviewed_path),
        "replay_source_sha256": _sha256(replay_source_path),
        "dataset_sha256": _sha256(output_path),
        "production_claim_eligible": False,
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the replay-safe semantic-v4 corpus")
    parser.add_argument("--stage-b-reviewed", type=Path, required=True)
    parser.add_argument("--stage-a-reviewed", type=Path, required=True)
    parser.add_argument("--replay-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay-target", type=int, default=REPLAY_TARGET)
    args = parser.parse_args()
    print(json.dumps(build_corpus(args.stage_b_reviewed, args.stage_a_reviewed, args.replay_source, args.output, replay_target=args.replay_target), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
