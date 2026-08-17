from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

from ml.features.schema import (
    CATEGORICAL_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    feature_vector,
)
from ml.tabular.train_catboost import load_rows

STACK_FEATURES = [
    "semantic_contradiction",
    "semantic_neutral",
    "catboost_probability",
    "hard_fail_count",
    "soft_warning_count",
]


def _stack_row(row: dict[str, Any], catboost_probability: float) -> list[float]:
    return [
        float(row["semantic_contradiction"]),
        float(row["semantic_neutral"]),
        float(catboost_probability),
        float(row["hard_fail_count"]),
        float(row["soft_warning_count"]),
    ]


def train(dataset_path: Path, artifact_dir: Path, folds: int = 5) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before training fusion artifacts") from exc

    rows = load_rows(dataset_path)
    training = [row for row in rows if row["split"] == "train" and row["label"] is not None]
    validation = [row for row in rows if row["split"] == "validation" and row["label"] is not None]
    calibration = [row for row in rows if row["split"] == "calibration" and row["label"] is not None]
    groups = [row["seed_id"] for row in training]
    unique_groups = sorted(set(groups))
    n_splits = min(folds, len(unique_groups))
    if n_splits < 2 or not calibration:
        raise ValueError("fusion requires at least two training groups and a calibration split")
    category_indexes = [FEATURE_NAMES.index(name) for name in CATEGORICAL_FEATURES]
    oof = [0.0] * len(training)
    splitter = GroupKFold(n_splits=n_splits)
    for train_indexes, holdout_indexes in splitter.split(training, groups=groups):
        fold_model = CatBoostClassifier(
            iterations=80,
            depth=4,
            learning_rate=0.07,
            loss_function="Logloss",
            random_seed=2026,
            verbose=False,
            allow_writing_files=False,
            auto_class_weights="Balanced",
        )
        fold_model.fit(
            [feature_vector(training[index]) for index in train_indexes],
            [training[index]["label"] for index in train_indexes],
            cat_features=category_indexes,
        )
        probabilities = fold_model.predict_proba(
            [feature_vector(training[index]) for index in holdout_indexes]
        )[:, 1]
        for index, probability in zip(holdout_indexes, probabilities, strict=True):
            oof[index] = float(probability)

    stacker = LogisticRegression(random_state=2026, max_iter=1000)
    stacker.fit(
        [_stack_row(row, probability) for row, probability in zip(training, oof, strict=True)],
        [row["label"] for row in training],
    )

    base_model = CatBoostClassifier(
        iterations=100,
        depth=5,
        learning_rate=0.05,
        loss_function="Logloss",
        random_seed=2026,
        verbose=False,
        allow_writing_files=False,
        auto_class_weights="Balanced",
    )
    base_model.fit(
        [feature_vector(row) for row in training],
        [row["label"] for row in training],
        cat_features=category_indexes,
    )
    calibration_cat = base_model.predict_proba([feature_vector(row) for row in calibration])[:, 1]
    calibration_stack = stacker.predict_proba(
        [_stack_row(row, probability) for row, probability in zip(calibration, calibration_cat, strict=True)]
    )[:, 1]
    calibrator = LogisticRegression(random_state=2026)
    calibrator.fit([[float(value)] for value in calibration_stack], [row["label"] for row in calibration])

    validation_cat = base_model.predict_proba([feature_vector(row) for row in validation])[:, 1]
    validation_stack = stacker.predict_proba(
        [_stack_row(row, probability) for row, probability in zip(validation, validation_cat, strict=True)]
    )[:, 1]
    validation_calibrated = calibrator.predict_proba(
        [[float(value)] for value in validation_stack]
    )[:, 1]
    valid_probabilities = [
        float(probability)
        for row, probability in zip(validation, validation_calibrated, strict=True)
        if row["label"] == 0
    ]
    if not valid_probabilities:
        raise ValueError("validation split requires legitimate examples for threshold selection")
    approve_threshold = min(max(valid_probabilities) + 0.01, 0.79)
    decline_threshold = 0.80

    artifact_dir.mkdir(parents=True, exist_ok=True)
    base_path = artifact_dir / "fusion-catboost-v1.cbm"
    fusion_path = artifact_dir / "stacker-calibrator-v1.pkl"
    base_model.save_model(base_path)
    fusion_path.write_bytes(pickle.dumps({"stacker": stacker, "calibrator": calibrator}))
    manifest = {
        "model_version": "stacker-calibrator-v1",
        "feature_version": FEATURE_VERSION,
        "stack_features": STACK_FEATURES,
        "base_artifact": base_path.name,
        "base_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        "fusion_artifact": fusion_path.name,
        "fusion_sha256": hashlib.sha256(fusion_path.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "oof_folds": n_splits,
        "calibration_rows": len(calibration),
        "threshold_selection_rows": len(validation),
        "approve_threshold": approve_threshold,
        "decline_threshold": decline_threshold,
        "random_seed": 2026,
    }
    (artifact_dir / "stacker-calibrator-v1.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("ml/data/generated/mandate-cart-pairs.jsonl"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/models"))
    args = parser.parse_args()
    print(json.dumps(train(args.dataset, args.artifacts), indent=2))


if __name__ == "__main__":
    main()
