from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ml.features.schema import (
    CATEGORICAL_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    FULL_STACK_FEATURES,
    feature_names_for_profile,
    feature_vector,
    stack_feature_names_for_profile,
)
from ml.fusion.policy_selection import (
    select_policy_threshold,
    target_rows,
    target_value,
)
from ml.tabular.train_catboost import (
    _require_binary_targets,
    load_rows,
    validate_feature_dataset,
)

STACK_FEATURES = FULL_STACK_FEATURES


def logistic_bundle(model: Any) -> dict[str, Any]:
    return {
        "classes": [int(value) for value in model.classes_],
        "coefficients": [float(value) for value in model.coef_[0]],
        "intercept": float(model.intercept_[0]),
    }


def logistic_probability(bundle: dict[str, Any], values: list[float]) -> float:
    raw = float(bundle["intercept"]) + sum(
        coefficient * value
        for coefficient, value in zip(bundle["coefficients"], values, strict=True)
    )
    return 1.0 / (1.0 + math.exp(-max(min(raw, 40), -40)))


def stack_features_for_profile(feature_profile: str) -> list[str]:
    return stack_feature_names_for_profile(feature_profile)


def _stack_row(
    row: dict[str, Any],
    catboost_probability: float,
    stack_features: list[str] | None = None,
) -> list[float]:
    values = {
        "semantic_contradiction": float(row["semantic_contradiction"]),
        "semantic_neutral": float(row["semantic_neutral"]),
        "catboost_probability": float(catboost_probability),
        "hard_fail_count": float(row["hard_fail_count"]),
        "soft_warning_count": float(row["soft_warning_count"]),
    }
    return [values[name] for name in stack_features or STACK_FEATURES]


def train(
    dataset_path: Path,
    artifact_dir: Path,
    folds: int = 5,
    feature_profile: str = "full-v2",
    target_mode: str = "binary_deviation",
) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold
    except ImportError as exc:
        raise RuntimeError(
            "Install services/api[ml] before training fusion artifacts"
        ) from exc

    rows = load_rows(dataset_path)
    feature_manifest = validate_feature_dataset(dataset_path, rows)
    selected_features = feature_names_for_profile(feature_profile)
    selected_stack_features = stack_features_for_profile(feature_profile)
    training = target_rows(rows, "train", target_mode)
    validation = target_rows(rows, "validation", target_mode)
    calibration = target_rows(rows, "calibration", target_mode)
    threshold_selection = [
        row
        for row in rows
        if row["split"] == "validation" and row.get("expected_treatment") is not None
    ]
    groups = [row["seed_id"] for row in training]
    unique_groups = sorted(set(groups))
    n_splits = min(folds, len(unique_groups))
    if n_splits < 2 or not calibration:
        raise ValueError(
            "fusion requires at least two training groups and a calibration split"
        )
    training_label_counts = _require_binary_targets(training, "train", target_mode)
    validation_label_counts = _require_binary_targets(
        validation, "validation", target_mode
    )
    calibration_label_counts = _require_binary_targets(
        calibration, "calibration", target_mode
    )
    category_indexes = [
        selected_features.index(name)
        for name in CATEGORICAL_FEATURES
        if name in selected_features
    ]
    oof = [math.nan] * len(training)
    splitter = GroupKFold(n_splits=n_splits)
    fold_summaries: list[dict[str, Any]] = []
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
            [
                feature_vector(training[index], selected_features)
                for index in train_indexes
            ],
            [target_value(training[index], target_mode) for index in train_indexes],
            cat_features=category_indexes,
        )
        probabilities = fold_model.predict_proba(
            [
                feature_vector(training[index], selected_features)
                for index in holdout_indexes
            ]
        )[:, 1]
        for index, probability in zip(holdout_indexes, probabilities, strict=True):
            oof[index] = float(probability)
        training_groups = {training[index]["seed_id"] for index in train_indexes}
        holdout_groups = {training[index]["seed_id"] for index in holdout_indexes}
        if training_groups.intersection(holdout_groups):
            raise ValueError("fusion OOF fold contains group leakage")
        fold_summaries.append(
            {
                "training_rows": len(train_indexes),
                "holdout_rows": len(holdout_indexes),
                "training_groups": len(training_groups),
                "holdout_groups": len(holdout_groups),
                "holdout_label_counts": {
                    str(label): sum(
                        target_value(training[index], target_mode) == label
                        for index in holdout_indexes
                    )
                    for label in (0, 1)
                },
            }
        )
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in oof):
        raise ValueError("fusion OOF predictions are incomplete or invalid")
    if max(oof) - min(oof) < 1e-6:
        raise ValueError("fusion OOF CatBoost predictions collapsed to a constant")

    stacker = LogisticRegression(random_state=2026, max_iter=1000)
    stacker.fit(
        [
            _stack_row(row, probability, selected_stack_features)
            for row, probability in zip(training, oof, strict=True)
        ],
        [target_value(row, target_mode) for row in training],
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
        [feature_vector(row, selected_features) for row in training],
        [target_value(row, target_mode) for row in training],
        cat_features=category_indexes,
    )
    calibration_cat = base_model.predict_proba(
        [feature_vector(row, selected_features) for row in calibration]
    )[:, 1]
    calibration_stack = stacker.predict_proba(
        [
            _stack_row(row, probability, selected_stack_features)
            for row, probability in zip(calibration, calibration_cat, strict=True)
        ]
    )[:, 1]
    calibrator = LogisticRegression(random_state=2026)
    calibrator.fit(
        [[float(value)] for value in calibration_stack],
        [target_value(row, target_mode) for row in calibration],
    )

    threshold_cat = base_model.predict_proba(
        [feature_vector(row, selected_features) for row in threshold_selection]
    )[:, 1]
    threshold_stack = [
        logistic_probability(
            logistic_bundle(stacker),
            _stack_row(row, float(probability), selected_stack_features),
        )
        for row, probability in zip(threshold_selection, threshold_cat, strict=True)
    ]
    threshold_probabilities = [
        logistic_probability(logistic_bundle(calibrator), [probability])
        for probability in threshold_stack
    ]
    threshold_result = select_policy_threshold(
        threshold_selection, threshold_probabilities, 0.10
    )
    step_up_threshold = float(threshold_result["threshold"])

    artifact_dir.mkdir(parents=True, exist_ok=True)
    base_path = artifact_dir / "fusion-catboost-v2.cbm"
    fusion_path = artifact_dir / "fusion-v2.json"
    temporary_base = artifact_dir / "fusion-catboost-v2.tmp.cbm"
    base_model.save_model(temporary_base, format="cbm")
    temporary_base.replace(base_path)
    temporary_fusion = artifact_dir / "fusion-v2.tmp.json"
    temporary_fusion.write_text(
        json.dumps(
            {
                "stacker": logistic_bundle(stacker),
                "calibrator": logistic_bundle(calibrator),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    temporary_fusion.replace(fusion_path)
    manifest = {
        "model_version": "fusion-v2",
        "catboost_version": "fusion-catboost-v2",
        "stacker_version": "logistic-stacker-v2",
        "calibrator_version": "platt-calibrator-v2",
        "feature_version": FEATURE_VERSION,
        "feature_profile": feature_profile,
        "feature_names": selected_features,
        "canonical_feature_names": FEATURE_NAMES,
        "categorical_features": [
            name for name in CATEGORICAL_FEATURES if name in selected_features
        ],
        "stack_features": selected_stack_features,
        "target_mode": target_mode,
        "base_artifact": base_path.name,
        "base_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        "fusion_artifact": fusion_path.name,
        "fusion_sha256": hashlib.sha256(fusion_path.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "feature_manifest_sha256": feature_manifest["manifest_sha256"],
        "dataset_version": str(rows[0].get("dataset_version", "unknown")),
        "semantic_model_versions": feature_manifest.get(
            "semantic_model_versions", ["unknown"]
        ),
        "semantic_predictions_sha256": feature_manifest.get(
            "semantic_predictions_sha256"
        ),
        "oof_folds": n_splits,
        "oof_fold_summaries": fold_summaries,
        "oof_probability_range": [min(oof), max(oof)],
        "training_rows": len(training),
        "training_groups": len(unique_groups),
        "training_label_counts": training_label_counts,
        "calibration_rows": len(calibration),
        "calibration_label_counts": calibration_label_counts,
        "threshold_selection_rows": len(threshold_selection),
        "validation_label_counts": validation_label_counts,
        "model_step_up_threshold": step_up_threshold,
        "false_step_up_target": 0.10,
        "threshold_selection_method": threshold_result["selection_method"],
        "threshold_selection_metrics": threshold_result,
        "validation_legitimate_rows": threshold_result["legitimate_rows"],
        "validation_false_step_up_count": threshold_result[
            "false_step_up_count"
        ],
        "validation_false_step_up_rate": threshold_result["false_step_up_rate"],
        "validation_violation_recall": threshold_result["violation_recall"],
        "validation_probability_range": [
            float(min(threshold_probabilities)),
            float(max(threshold_probabilities)),
        ],
        "model_hold_enabled": False,
        "model_hold_threshold": None,
        "serving_approved": False,
        "random_seed": 2026,
    }
    manifest_path = artifact_dir / "fusion-v2.manifest.json"
    temporary_manifest = artifact_dir / "fusion-v2.manifest.tmp.json"
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    temporary_manifest.replace(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("ml/data/generated/mandate-cart-pairs.jsonl"),
    )
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--feature-profile", default="full-v2")
    parser.add_argument("--target-mode", default="binary_deviation")
    args = parser.parse_args()
    print(
        json.dumps(
            train(
                args.dataset,
                args.artifacts,
                feature_profile=args.feature_profile,
                target_mode=args.target_mode,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
