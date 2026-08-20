from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ml.features.schema import (
    CATEGORICAL_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    feature_names_for_profile,
    feature_vector,
)
from ml.fusion.policy_selection import target_rows, target_value


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as source:
        for line in source:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def validate_feature_dataset(
    path: Path, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest_path = path.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        raise ValueError("feature dataset requires its checksum-bound manifest")
    manifest = json.loads(manifest_path.read_text())
    dataset_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest.get("features_sha256") != dataset_sha256:
        raise ValueError("feature dataset checksum does not match its manifest")
    if manifest.get("feature_version") != FEATURE_VERSION:
        raise ValueError("feature dataset version is incompatible with this trainer")
    if manifest.get("feature_names") != FEATURE_NAMES:
        raise ValueError("feature dataset order is incompatible with this trainer")
    semantic_versions = manifest.get("semantic_model_versions")
    semantic_sha256 = manifest.get("semantic_predictions_sha256")
    if not isinstance(semantic_versions, list) or not semantic_versions:
        raise ValueError("feature manifest is missing semantic model versions")
    if not isinstance(semantic_sha256, str) or len(semantic_sha256) != 64:
        raise ValueError("feature manifest is missing the semantic prediction binding")
    if not rows:
        raise ValueError("feature dataset is empty")
    example_ids: set[str] = set()
    group_splits: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        example_id = str(row.get("example_id", ""))
        if not example_id or example_id in example_ids:
            raise ValueError("feature dataset contains an empty or duplicate example ID")
        example_ids.add(example_id)
        group_splits[str(row["seed_id"])].add(str(row["split"]))
        label = row.get("label")
        if label is not None and label not in (0, 1):
            raise ValueError("feature labels must be binary or null")
        values = feature_vector(row)
        for index, value in enumerate(values):
            if index < len(FEATURE_NAMES) - len(CATEGORICAL_FEATURES):
                if not math.isfinite(float(value)):
                    raise ValueError("feature dataset contains a non-finite numeric value")
            elif not str(value):
                raise ValueError("feature dataset contains an empty categorical value")
    if any(len(splits) != 1 for splits in group_splits.values()):
        raise ValueError("feature dataset contains cross-split group leakage")
    return {
        **manifest,
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "rows": len(rows),
        "groups": len(group_splits),
        "label_counts": {
            str(label): count for label, count in sorted(
                Counter(row.get("label") for row in rows).items(),
                key=lambda item: str(item[0]),
            )
        },
    }


def labeled(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["split"] == split and row["label"] is not None]


def matrix(
    rows: list[dict[str, Any]], feature_names: list[str] | None = None
) -> list[list[float | str]]:
    return [feature_vector(row, feature_names) for row in rows]


def _require_binary(rows: list[dict[str, Any]], split: str) -> dict[str, int]:
    counts = Counter(int(row["label"]) for row in rows)
    if set(counts) != {0, 1}:
        raise ValueError(f"{split} split must contain both binary classes")
    return {str(label): counts[label] for label in (0, 1)}


def _require_binary_targets(
    rows: list[dict[str, Any]], split: str, target_mode: str
) -> dict[str, int]:
    counts = Counter(target_value(row, target_mode) for row in rows)
    if set(counts) != {0, 1}:
        raise ValueError(f"{split} split must contain both target classes")
    return {str(label): counts[label] for label in (0, 1)}


def train(
    dataset_path: Path,
    artifact_dir: Path,
    iterations: int = 120,
    feature_profile: str = "full-v2",
    target_mode: str = "binary_deviation",
    training_split: str = "train",
    validation_split: str = "validation",
) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before training CatBoost") from exc

    rows = load_rows(dataset_path)
    feature_manifest = validate_feature_dataset(dataset_path, rows)
    selected_features = feature_names_for_profile(feature_profile)
    training = target_rows(rows, training_split, target_mode)
    if validation_split == "internal_grouped_20pct":
        complete_training = training
        validation = [
            row
            for row in complete_training
            if int(hashlib.sha256(str(row["seed_id"]).encode()).hexdigest(), 16) % 5
            == 0
        ]
        validation_groups = {str(row["seed_id"]) for row in validation}
        training = [
            row
            for row in complete_training
            if str(row["seed_id"]) not in validation_groups
        ]
    else:
        validation = target_rows(rows, validation_split, target_mode)
    if not training or not validation:
        raise ValueError("dataset must contain targeted training and validation groups")
    training_label_counts = _require_binary_targets(
        training, training_split, target_mode
    )
    validation_label_counts = _require_binary_targets(
        validation, validation_split, target_mode
    )
    category_indexes = [
        selected_features.index(name)
        for name in CATEGORICAL_FEATURES
        if name in selected_features
    ]
    model = CatBoostClassifier(
        iterations=iterations,
        depth=5,
        learning_rate=0.05,
        loss_function="Logloss",
        eval_metric="PRAUC",
        random_seed=2026,
        verbose=False,
        allow_writing_files=False,
        auto_class_weights="Balanced",
    )
    model.fit(
        matrix(training, selected_features),
        [target_value(row, target_mode) for row in training],
        cat_features=category_indexes,
        eval_set=(
            matrix(validation, selected_features),
            [target_value(row, target_mode) for row in validation],
        ),
        early_stopping_rounds=25,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "catboost-v1.cbm"
    temporary_model = artifact_dir / "catboost-v1.tmp.cbm"
    model.save_model(temporary_model, format="cbm")
    temporary_model.replace(model_path)
    manifest = {
        "model_version": "catboost-v1",
        "kind": "catboost_binary_classifier",
        "feature_version": FEATURE_VERSION,
        "feature_profile": feature_profile,
        "feature_names": selected_features,
        "canonical_feature_names": FEATURE_NAMES,
        "categorical_features": [
            name for name in CATEGORICAL_FEATURES if name in selected_features
        ],
        "target_mode": target_mode,
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "feature_manifest_sha256": feature_manifest["manifest_sha256"],
        "semantic_model_versions": feature_manifest["semantic_model_versions"],
        "semantic_predictions_sha256": feature_manifest[
            "semantic_predictions_sha256"
        ],
        "artifact_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "training_rows": len(training),
        "validation_rows": len(validation),
        "training_split": training_split,
        "validation_split": validation_split,
        "training_label_counts": training_label_counts,
        "validation_label_counts": validation_label_counts,
        "tree_count": int(model.tree_count_),
        "best_iteration": int(model.get_best_iteration()),
        "random_seed": 2026,
    }
    manifest_path = artifact_dir / "catboost-v1.manifest.json"
    temporary_manifest = artifact_dir / "catboost-v1.manifest.tmp.json"
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    temporary_manifest.replace(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("ml/data/generated/mandate-cart-pairs.jsonl"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--feature-profile", default="full-v2")
    parser.add_argument("--target-mode", default="binary_deviation")
    parser.add_argument("--training-split", default="train")
    parser.add_argument("--validation-split", default="validation")
    args = parser.parse_args()
    print(
        json.dumps(
            train(
                args.dataset,
                args.artifacts,
                args.iterations,
                args.feature_profile,
                args.target_mode,
                args.training_split,
                args.validation_split,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
