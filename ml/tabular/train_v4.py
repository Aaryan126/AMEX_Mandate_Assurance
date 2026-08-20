from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from app.feature_contract_v3 import (
    CATEGORICAL_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    feature_names_for_profile,
)
from ml.features.schema_v3 import feature_vector
from ml.fusion.policy_selection import select_policy_configuration, target_value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def _target(row: dict[str, Any]) -> int:
    value = target_value(row, "policy_intervention")
    if value is None:
        raise ValueError("v4 training requires a reviewed policy target")
    return value


def _matrix(rows: list[dict[str, Any]], names: list[str]) -> list[list[float | str]]:
    return [feature_vector(row, names) for row in rows]


def _fit(
    rows: list[dict[str, Any]],
    names: list[str],
    weights: list[float],
    *,
    depth: int,
    l2: float,
    iterations: int,
    validation: list[dict[str, Any]] | None = None,
):
    from catboost import CatBoostClassifier

    category_indexes = [
        names.index(name) for name in CATEGORICAL_FEATURES if name in names
    ]
    model = CatBoostClassifier(
        iterations=iterations,
        depth=depth,
        l2_leaf_reg=l2,
        learning_rate=0.05,
        loss_function="Logloss",
        eval_metric="PRAUC",
        random_seed=2030,
        verbose=False,
        allow_writing_files=False,
    )
    kwargs: dict[str, Any] = {}
    if validation:
        kwargs["eval_set"] = (
            _matrix(validation, names),
            [_target(row) for row in validation],
        )
        kwargs["early_stopping_rounds"] = 40
    model.fit(
        _matrix(rows, names),
        [_target(row) for row in rows],
        sample_weight=weights,
        cat_features=category_indexes,
        **kwargs,
    )
    return model


def _split_training(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validation = [
        row
        for row in rows
        if int(hashlib.sha256(str(row["seed_id"]).encode()).hexdigest(), 16) % 5 == 0
    ]
    groups = {str(row["seed_id"]) for row in validation}
    training = [row for row in rows if str(row["seed_id"]) not in groups]
    if not training or not validation:
        raise ValueError("grouped internal split is empty")
    return training, validation


def _confidence_weights(rows: list[dict[str, Any]]) -> list[float]:
    return [0.5 if row.get("label_source") == "weak_policy_v4" else 1.0 for row in rows]


def _jtt_multipliers(rows: list[dict[str, Any]], names: list[str]) -> dict[str, float]:
    predictions: dict[str, float] = {}
    for fold in range(5):
        held = [
            row
            for row in rows
            if int(hashlib.sha256(str(row["seed_id"]).encode()).hexdigest(), 16) % 5
            == fold
        ]
        held_ids = {str(row["example_id"]) for row in held}
        train = [row for row in rows if str(row["example_id"]) not in held_ids]
        if not held or not train:
            raise ValueError("OOF JTT fold is empty")
        model = _fit(train, names, _confidence_weights(train), depth=5, l2=6, iterations=180)
        values = model.predict_proba(_matrix(held, names))[:, 1]
        predictions.update(
            {
                str(row["example_id"]): float(value)
                for row, value in zip(held, values, strict=True)
            }
        )
    if len(predictions) != len(rows):
        raise ValueError("OOF JTT predictions do not cover training rows")
    return {
        str(row["example_id"]): (
            3.0
            if _target(row) == 1 and predictions[str(row["example_id"])] < 0.5
            else 1.5
            if _target(row) == 0 and predictions[str(row["example_id"])] >= 0.5
            else 1.0
        )
        for row in rows
    }


def _calibrated(calibrator, probabilities) -> list[float]:
    logits = [
        [math.log(value / (1 - value))]
        for raw in probabilities
        for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]
    ]
    return [float(value) for value in calibrator.predict_proba(logits)[:, 1]]


def train(features_path: Path, output_dir: Path) -> dict[str, Any]:
    from joblib import dump
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score

    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite v4 training output: {output_dir}")
    manifest_path = features_path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("features_sha256") != _sha256(features_path):
        raise ValueError("features-v3 checksum mismatch")
    if manifest.get("feature_version") != FEATURE_VERSION or manifest.get("feature_names") != FEATURE_NAMES:
        raise ValueError("features-v3 contract mismatch")
    rows = _rows(features_path)
    train_rows = [row for row in rows if row["split"] == "train_fit"]
    calibration = [row for row in rows if row["split"] == "calibration"]
    tuning = [row for row in rows if row["split"] == "policy_tuning"]
    if len(train_rows) != 10_000 or len(calibration) != 1_500 or len(tuning) != 1_500:
        raise ValueError("v4 development role counts are incompatible")
    internal_train, internal_validation = _split_training(train_rows)
    jtt = _jtt_multipliers(train_rows, feature_names_for_profile("full-v3"))
    profiles = ("full-v3", "shortcut-safe-v3", "no-semantic-v3")
    weighting = ("none", "confidence", "jtt")
    experiments: list[dict[str, Any]] = []
    best: tuple[float, Any, list[str], str, str] | None = None
    for profile in profiles:
        names = feature_names_for_profile(profile)
        for weight_name in weighting:
            base = _confidence_weights(internal_train)
            weights = [
                (1.0 if weight_name == "none" else base[index])
                * (jtt[str(row["example_id"])] if weight_name == "jtt" else 1.0)
                for index, row in enumerate(internal_train)
            ]
            model = _fit(
                internal_train,
                names,
                weights,
                depth=5,
                l2=6,
                iterations=300,
                validation=internal_validation,
            )
            probability = model.predict_proba(_matrix(internal_validation, names))[:, 1]
            pr_auc = float(
                average_precision_score(
                    [_target(row) for row in internal_validation], probability
                )
            )
            experiment = {
                "feature_profile": profile,
                "weighting": weight_name,
                "depth": 5,
                "l2_leaf_reg": 6,
                "pr_auc": pr_auc,
                "tree_count": int(model.tree_count_),
            }
            experiments.append(experiment)
            rank = (pr_auc, model, names, profile, weight_name)
            if best is None or rank[0] > best[0]:
                best = rank
    assert best is not None
    _, _, selected_names, selected_profile, selected_weighting = best
    final_weights = _confidence_weights(train_rows)
    if selected_weighting == "none":
        final_weights = [1.0] * len(train_rows)
    elif selected_weighting == "jtt":
        final_weights = [
            weight * jtt[str(row["example_id"])]
            for row, weight in zip(train_rows, final_weights, strict=True)
        ]
    final_model = _fit(
        train_rows,
        selected_names,
        final_weights,
        depth=5,
        l2=6,
        iterations=max(120, int(best[1].tree_count_)),
    )
    calibration_raw = final_model.predict_proba(_matrix(calibration, selected_names))[:, 1]
    calibration_logits = [
        [math.log(value / (1 - value))]
        for raw in calibration_raw
        for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]
    ]
    calibrator = LogisticRegression(random_state=2030)
    calibrator.fit(calibration_logits, [_target(row) for row in calibration])
    tuning_raw = final_model.predict_proba(_matrix(tuning, selected_names))[:, 1]
    tuning_probability = _calibrated(calibrator, tuning_raw)
    policy = select_policy_configuration(tuning, tuning_probability)
    output_dir.mkdir(parents=True, exist_ok=False)
    model_path = output_dir / "catboost-v4.cbm"
    final_model.save_model(model_path, format="cbm")
    calibrator_path = output_dir / "platt-calibrator-v4.joblib"
    dump(calibrator, calibrator_path)
    policy_path = output_dir / "policy-v4.json"
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")
    model_manifest = {
        "model_version": "catboost-v4",
        "feature_version": FEATURE_VERSION,
        "feature_names": selected_names,
        "feature_profile": selected_profile,
        "weighting": selected_weighting,
        "features_sha256": _sha256(features_path),
        "features_manifest_sha256": _sha256(manifest_path),
        "semantic_predictions_sha256": manifest["semantic_predictions_sha256"],
        "model_sha256": _sha256(model_path),
        "calibrator_sha256": _sha256(calibrator_path),
        "policy_sha256": _sha256(policy_path),
        "training_rows": len(train_rows),
        "calibration_rows": len(calibration),
        "policy_tuning_rows": len(tuning),
        "candidate_rows_accessed": 0,
        "label_sources": dict(sorted(Counter(row["label_source"] for row in train_rows).items())),
        "production_claim_eligible": False,
    }
    model_manifest_path = output_dir / "catboost-v4.manifest.json"
    model_manifest_path.write_text(json.dumps(model_manifest, indent=2, sort_keys=True) + "\n")
    lock = {
        "lock_version": "candidate-pre-evaluation-lock-v4",
        "features_sha256": _sha256(features_path),
        "model_sha256": _sha256(model_path),
        "model_manifest_sha256": _sha256(model_manifest_path),
        "calibrator_sha256": _sha256(calibrator_path),
        "policy_sha256": _sha256(policy_path),
        "candidate_rows_accessed": 0,
        "status": "FROZEN_UNEVALUATED",
    }
    lock_path = output_dir / "candidate-pre-evaluation-lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    report = {
        "training_version": "development-v4-data-policy",
        "selected_profile": selected_profile,
        "selected_weighting": selected_weighting,
        "experiments": sorted(experiments, key=lambda value: value["pr_auc"], reverse=True),
        "policy_selection": policy,
        "artifacts": model_manifest,
        "candidate_pre_evaluation_lock_sha256": _sha256(lock_path),
    }
    (output_dir / "training-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(train(args.features, args.output), indent=2))


if __name__ == "__main__":
    main()
