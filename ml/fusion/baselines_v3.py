from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ml.evaluation.metrics import by_attack_family, expected_calibration_error
from ml.features.schema import feature_vector
from ml.fusion.policy_selection import (
    policy_metrics,
    predict_policy_treatment,
    select_policy_threshold,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def _labels(rows: list[dict[str, Any]]) -> list[int]:
    return [int(row["expected_treatment"] != "APPROVE") for row in rows]


def _quality(labels: list[int], probabilities: list[float]) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss

    return {
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "brier": float(brier_score_loss(labels, probabilities)),
        "expected_calibration_error": expected_calibration_error(
            labels, probabilities
        ),
    }


def _policy_report(
    tuning: list[dict[str, Any]],
    tuning_probabilities: list[float],
    selection: list[dict[str, Any]],
    selection_probabilities: list[float],
) -> dict[str, Any]:
    threshold = select_policy_threshold(tuning, tuning_probabilities)
    metrics = policy_metrics(selection, selection_probabilities, threshold["threshold"])
    predicted = [
        predict_policy_treatment(row, probability, threshold["threshold"])
        for row, probability in zip(selection, selection_probabilities, strict=True)
    ]
    return {
        "threshold_selection": threshold,
        "candidate_selection_policy": metrics,
        "by_attack_family": by_attack_family(selection, predicted),
    }


def run(
    features_path: Path,
    catboost_model_path: Path,
    catboost_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    from catboost import CatBoostClassifier
    from joblib import dump
    from sklearn.linear_model import LogisticRegression

    rows = _rows(features_path)
    roles = {
        role: [row for row in rows if row["split"] == role]
        for role in ("calibration", "policy_tuning", "candidate_selection")
    }
    if any(not values for values in roles.values()):
        raise ValueError("baseline v3 requires all three held-out development roles")
    catboost_manifest = json.loads(catboost_manifest_path.read_text())
    if catboost_manifest["dataset_sha256"] != _sha256(features_path):
        raise ValueError("CatBoost artifact is not bound to the v3 feature dataset")
    model = CatBoostClassifier()
    model.load_model(catboost_model_path)
    feature_names = catboost_manifest["feature_names"]

    def catboost_probabilities(values: list[dict[str, Any]]) -> list[float]:
        return [
            float(value)
            for value in model.predict_proba(
                [feature_vector(row, feature_names) for row in values]
            )[:, 1]
        ]

    raw = {role: catboost_probabilities(values) for role, values in roles.items()}
    calibration_labels = _labels(roles["calibration"])
    calibration_logits = [
        [math.log(min(max(value, 1e-6), 1 - 1e-6) / (1 - min(max(value, 1e-6), 1 - 1e-6)))]
        for value in raw["calibration"]
    ]
    calibrator = LogisticRegression(random_state=2029)
    calibrator.fit(calibration_logits, calibration_labels)

    def calibrated(values: list[float]) -> list[float]:
        logits = [
            [math.log(min(max(value, 1e-6), 1 - 1e-6) / (1 - min(max(value, 1e-6), 1 - 1e-6)))]
            for value in values
        ]
        return [float(value) for value in calibrator.predict_proba(logits)[:, 1]]

    calibrated_probabilities = {
        role: calibrated(values) for role, values in raw.items()
    }
    semantic = {
        role: [
            max(float(row["semantic_contradiction"]), float(row["semantic_neutral"]))
            for row in values
        ]
        for role, values in roles.items()
    }
    deterministic = {
        role: [
            min(1.0, float(row["hard_fail_count"] > 0)) for row in values
        ]
        for role, values in roles.items()
    }

    candidates: dict[str, Any] = {}
    for name, probabilities in (
        ("deterministic_policy", deterministic),
        ("frozen_semantic", semantic),
        ("catboost", raw),
        ("calibrated_catboost", calibrated_probabilities),
    ):
        selection = probabilities["candidate_selection"]
        candidates[name] = {
            "candidate_selection_quality": _quality(
                _labels(roles["candidate_selection"]), selection
            ),
            **_policy_report(
                roles["policy_tuning"],
                probabilities["policy_tuning"],
                roles["candidate_selection"],
                selection,
            ),
        }

    raw_quality = candidates["catboost"]["candidate_selection_quality"]
    calibrated_quality = candidates["calibrated_catboost"][
        "candidate_selection_quality"
    ]
    selected_name = (
        "calibrated_catboost"
        if calibrated_quality["expected_calibration_error"]
        <= raw_quality["expected_calibration_error"]
        and calibrated_quality["pr_auc"] >= raw_quality["pr_auc"] - 0.01
        else "catboost"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    calibrator_path = output_dir / "platt-calibrator-v3.joblib"
    dump(calibrator, calibrator_path)
    report = {
        "baseline_version": "development-baselines-v3",
        "features_sha256": _sha256(features_path),
        "catboost_sha256": _sha256(catboost_model_path),
        "catboost_manifest_sha256": _sha256(catboost_manifest_path),
        "calibrator_sha256": _sha256(calibrator_path),
        "role_counts": {key: len(value) for key, value in roles.items()},
        "candidates": candidates,
        "selected_candidate": selected_name,
        "fusion_evaluated": False,
        "fusion_reason": (
            "No independently trained leakage-safe fusion signal was available; CatBoost is the "
            "declared default and semantic probabilities are already included as inputs."
        ),
        "production_claim_eligible": False,
    }
    report_path = output_dir / "baseline-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--catboost-model", type=Path, required=True)
    parser.add_argument("--catboost-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.features,
                args.catboost_model,
                args.catboost_manifest,
                args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
