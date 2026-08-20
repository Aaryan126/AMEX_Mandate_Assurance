from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from joblib import load
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss, recall_score

from ml.evaluation.metrics import expected_calibration_error
from ml.features.schema import feature_vector
from ml.fusion.baselines_v3 import _quality
from ml.fusion.policy_selection import policy_metrics, predict_policy_treatment, select_policy_configuration

SEMANTIC_RECALL_MIN = 0.70
FALSE_STEP_UP_MAX = 0.10
FALSE_DECLINE_MAX = 0.02
OPERATIONAL_RECALL_REGRESSION_MAX = 0.01
EXPECTED_CALIBRATION_ERROR_MAX = 0.08
MACRO_F1_REGRESSION_MAX = 0.01
MINORITY_RECALL_IMPROVEMENT_MIN = 0.03


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def _logits(values: Any) -> list[list[float]]:
    return [
        [math.log(value / (1 - value))]
        for raw in values
        for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]
    ]


def semantic_metrics(rows: list[dict[str, Any]], split: str) -> dict[str, Any]:
    values = [row for row in rows if row.get("split") == split]
    if not values:
        raise ValueError(f"semantic metrics have no {split} rows")
    labels = [int(row["label"]) for row in values]
    probabilities = [
        [float(row["contradiction"]), float(row["neutral"]), float(row["entailment"])]
        for row in values
    ]
    predicted = [max(range(3), key=probability.__getitem__) for probability in probabilities]
    recalls = recall_score(labels, predicted, labels=[0, 1, 2], average=None, zero_division=0)
    confidence = [max(value) for value in probabilities]
    correct = [int(actual == result) for actual, result in zip(labels, predicted, strict=True)]
    return {
        "rows": len(values),
        "accuracy": float(accuracy_score(labels, predicted)),
        "macro_f1": float(f1_score(labels, predicted, average="macro", zero_division=0)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1, 2])),
        "confidence_ece": expected_calibration_error(correct, confidence),
        "recall": {
            "CONTRADICTION": float(recalls[0]),
            "NEUTRAL": float(recalls[1]),
            "ENTAILMENT": float(recalls[2]),
        },
        "minority_mean_recall": float((recalls[0] + recalls[1]) / 2),
    }


def reviewed_semantic_recall(
    rows: list[dict[str, Any]], probabilities: list[float], policy: dict[str, Any]
) -> dict[str, Any]:
    indexes = [index for index, row in enumerate(rows) if row.get("label_source") == "llm_assisted_v4"]
    violations = [index for index in indexes if rows[index]["expected_treatment"] != "APPROVE"]
    if not indexes or not violations:
        raise ValueError("Stage C1 policy gate requires reviewed semantic rows and violations")
    predicted = [
        predict_policy_treatment(
            row,
            probability,
            float(policy["threshold"]),
            semantic_contradiction_threshold=policy.get("semantic_contradiction_threshold"),
            semantic_neutral_threshold=policy.get("semantic_neutral_threshold"),
        )
        for row, probability in zip(rows, probabilities, strict=True)
    ]
    return {
        "rows": len(indexes),
        "violation_rows": len(violations),
        "recall": sum(predicted[index] != "APPROVE" for index in violations) / len(violations),
    }


def _policy_quality(rows: list[dict[str, Any]], probabilities: list[float], policy: dict[str, Any]) -> dict[str, Any]:
    quality = _quality([int(row["expected_treatment"] != "APPROVE") for row in rows], probabilities)
    quality["expected_calibration_error"] = expected_calibration_error(
        [int(row["expected_treatment"] != "APPROVE") for row in rows], probabilities
    )
    return {
        "quality": quality,
        "policy": policy_metrics(
            rows,
            probabilities,
            float(policy["threshold"]),
            semantic_contradiction_threshold=policy.get("semantic_contradiction_threshold"),
            semantic_neutral_threshold=policy.get("semantic_neutral_threshold"),
        ),
        "reviewed_semantic": reviewed_semantic_recall(rows, probabilities, policy),
        "configuration": policy,
    }


def evaluate(
    c1_features_path: Path,
    stage_b_features_path: Path,
    baseline_semantic_path: Path,
    c1_semantic_path: Path,
    stage_b_policy_path: Path,
    v3_model_path: Path,
    v3_manifest_path: Path,
    v3_calibrator_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    from catboost import CatBoostClassifier

    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite Stage C1 gate: {output_path}")
    c1_rows = _jsonl(c1_features_path)
    if {row["split"] for row in c1_rows} != {"calibration", "policy_tuning"}:
        raise ValueError("Stage C1 gate received candidate or training features")
    if len(c1_rows) != 2_400:
        raise ValueError("Stage C1 gate requires 2,400 candidate-free development rows")
    calibration = [row for row in c1_rows if row["split"] == "calibration"]
    tuning = [row for row in c1_rows if row["split"] == "policy_tuning"]
    manifest = json.loads(v3_manifest_path.read_text())
    if manifest.get("artifact_sha256") != _sha256(v3_model_path):
        raise ValueError("Stage C1 locked v3 model hash mismatch")
    model = CatBoostClassifier()
    model.load_model(v3_model_path)
    calibration_raw = model.predict_proba([feature_vector(row, manifest["feature_names"]) for row in calibration])[:, 1]
    c1_calibrator = LogisticRegression(random_state=2032)
    c1_calibrator.fit(_logits(calibration_raw), [int(row["expected_treatment"] != "APPROVE") for row in calibration])
    tuning_raw = model.predict_proba([feature_vector(row, manifest["feature_names"]) for row in tuning])[:, 1]
    c1_probability = [float(value) for value in c1_calibrator.predict_proba(_logits(tuning_raw))[:, 1]]
    c1_policy = select_policy_configuration(tuning, c1_probability)
    c1_result = _policy_quality(tuning, c1_probability, c1_policy)

    tuning_ids = {row["example_id"] for row in tuning}
    stage_b_tuning = [
        row
        for row in _jsonl(stage_b_features_path)
        if row.get("split") == "policy_tuning" and row["example_id"] in tuning_ids
    ]
    if len(stage_b_tuning) != len(tuning) or {row["example_id"] for row in stage_b_tuning} != tuning_ids:
        raise ValueError("Stage B and Stage C1 policy rows do not align")
    stage_b_tuning.sort(key=lambda row: row["example_id"])
    tuning.sort(key=lambda row: row["example_id"])
    baseline_raw = model.predict_proba([feature_vector(row, manifest["feature_names"]) for row in stage_b_tuning])[:, 1]
    baseline_probability = [
        float(value) for value in load(v3_calibrator_path).predict_proba(_logits(baseline_raw))[:, 1]
    ]
    baseline_policy = json.loads(stage_b_policy_path.read_text())
    baseline_result = _policy_quality(stage_b_tuning, baseline_probability, baseline_policy)

    baseline_semantic = _jsonl(baseline_semantic_path)
    c1_semantic = _jsonl(c1_semantic_path)
    semantic = {
        "baseline": {
            split: semantic_metrics(baseline_semantic, split)
            for split in ("validation", "calibration")
        },
        "stage_c1": {
            split: semantic_metrics(c1_semantic, split)
            for split in ("validation", "calibration")
        },
    }
    baseline_validation = semantic["baseline"]["validation"]
    c1_validation = semantic["stage_c1"]["validation"]
    checks = {
        "semantic_policy_recall": c1_result["reviewed_semantic"]["recall"] >= SEMANTIC_RECALL_MIN,
        "false_step_up": c1_result["policy"]["false_step_up_rate"] <= FALSE_STEP_UP_MAX,
        "false_decline": c1_result["policy"]["false_decline_rate"] <= FALSE_DECLINE_MAX,
        "operational_recall_no_regression": c1_result["policy"]["violation_recall"]
        >= baseline_result["policy"]["violation_recall"] - OPERATIONAL_RECALL_REGRESSION_MAX,
        "calibration": c1_result["quality"]["expected_calibration_error"] <= EXPECTED_CALIBRATION_ERROR_MAX,
        "semantic_macro_f1_no_regression": c1_validation["macro_f1"]
        >= baseline_validation["macro_f1"] - MACRO_F1_REGRESSION_MAX,
        "minority_recall_improvement": c1_validation["minority_mean_recall"]
        >= baseline_validation["minority_mean_recall"] + MINORITY_RECALL_IMPROVEMENT_MIN,
    }
    passed = all(checks.values())
    report = {
        "evaluation_version": "stage-c1-no-spend-gate-v1",
        "status": "PROCEED_STAGE_C2" if passed else "STOP_STAGE_C1",
        "bindings": {
            "c1_features_sha256": _sha256(c1_features_path),
            "baseline_semantic_sha256": _sha256(baseline_semantic_path),
            "c1_semantic_sha256": _sha256(c1_semantic_path),
            "stage_b_policy_sha256": _sha256(stage_b_policy_path),
        },
        "semantic": semantic,
        "stage_b_on_same_policy_role": baseline_result,
        "stage_c1_on_policy_role": c1_result,
        "thresholds": {
            "semantic_recall_min": SEMANTIC_RECALL_MIN,
            "false_step_up_max": FALSE_STEP_UP_MAX,
            "false_decline_max": FALSE_DECLINE_MAX,
            "operational_recall_regression_max": OPERATIONAL_RECALL_REGRESSION_MAX,
            "expected_calibration_error_max": EXPECTED_CALIBRATION_ERROR_MAX,
            "macro_f1_regression_max": MACRO_F1_REGRESSION_MAX,
            "minority_recall_improvement_min": MINORITY_RECALL_IMPROVEMENT_MIN,
        },
        "checks": checks,
        "candidate_rows_accessed": 0,
        "candidate_labels_accessed": 0,
        "llm_spend_authorized": passed,
        "stage_c2_authorized": passed,
        "production_claim_eligible": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the Stage C1 no-spend gate")
    parser.add_argument("--c1-features", type=Path, required=True)
    parser.add_argument("--stage-b-features", type=Path, required=True)
    parser.add_argument("--baseline-semantic", type=Path, required=True)
    parser.add_argument("--c1-semantic", type=Path, required=True)
    parser.add_argument("--stage-b-policy", type=Path, required=True)
    parser.add_argument("--v3-model", type=Path, required=True)
    parser.add_argument("--v3-manifest", type=Path, required=True)
    parser.add_argument("--v3-calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(
        args.c1_features,
        args.stage_b_features,
        args.baseline_semantic,
        args.c1_semantic,
        args.stage_b_policy,
        args.v3_model,
        args.v3_manifest,
        args.v3_calibrator,
        args.output,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
