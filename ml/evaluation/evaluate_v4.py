from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ml.evaluation.metrics import by_attack_family, expected_calibration_error
from ml.features.schema import feature_vector as feature_vector_v2
from ml.features.schema_v3 import feature_vector as feature_vector_v3
from ml.fusion.baselines_v3 import _quality
from ml.fusion.policy_selection import policy_metrics, predict_policy_treatment

GATES = {
    "operational_recall_min": 0.90,
    "false_step_up_max": 0.10,
    "false_decline_max": 0.02,
    "expected_calibration_error_max": 0.08,
    "supported_family_recall_min": 0.80,
    "supported_family_min_violations": 50,
    "reviewed_none_recall_min": 0.80,
    "pr_auc_regression_max": 0.01,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _calibrated(calibrator, values) -> list[float]:
    logits = [
        [math.log(value / (1 - value))]
        for raw in values
        for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]
    ]
    return [float(value) for value in calibrator.predict_proba(logits)[:, 1]]


def _predicted(rows, probabilities, policy) -> list[str]:
    return [
        predict_policy_treatment(
            row,
            probability,
            float(policy["threshold"]),
            semantic_contradiction_threshold=policy.get("semantic_contradiction_threshold"),
            semantic_neutral_threshold=policy.get("semantic_neutral_threshold"),
        )
        for row, probability in zip(rows, probabilities, strict=True)
    ]


def gate_report(
    quality: dict[str, float],
    policy: dict[str, Any],
    families: dict[str, dict[str, Any]],
    reviewed_none_recall: float,
    baseline_pr_auc: float,
) -> dict[str, Any]:
    supported = {
        family: value
        for family, value in families.items()
        if int(value["violation_rows"]) >= GATES["supported_family_min_violations"]
    }
    failures = {
        family: value["violation_recall"]
        for family, value in supported.items()
        if float(value["violation_recall"]) < GATES["supported_family_recall_min"]
    }
    checks = {
        "operational_recall": policy["violation_recall"] >= GATES["operational_recall_min"],
        "false_step_up": policy["false_step_up_rate"] <= GATES["false_step_up_max"],
        "false_decline": policy["false_decline_rate"] <= GATES["false_decline_max"],
        "calibration": quality["expected_calibration_error"] <= GATES["expected_calibration_error_max"],
        "supported_families": not failures,
        "reviewed_none": reviewed_none_recall >= GATES["reviewed_none_recall_min"],
        "pr_auc_regression": quality["pr_auc"] >= baseline_pr_auc - GATES["pr_auc_regression_max"],
    }
    return {
        "thresholds": GATES,
        "checks": checks,
        "supported_families": sorted(supported),
        "family_failures": failures,
        "all_passed": all(checks.values()),
    }


def evaluate(
    features_path: Path,
    selection_ledger_path: Path,
    v4_dir: Path,
    v3_model_path: Path,
    v3_manifest_path: Path,
    v3_calibrator_path: Path,
    v3_baseline_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    from catboost import CatBoostClassifier
    from joblib import load

    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite candidate evaluation: {output_path}")
    lock_path = v4_dir / "candidate-pre-evaluation-lock.json"
    lock = json.loads(lock_path.read_text())
    bindings = {
        "features_sha256": _sha256(features_path),
        "model_sha256": _sha256(v4_dir / "catboost-v4.cbm"),
        "model_manifest_sha256": _sha256(v4_dir / "catboost-v4.manifest.json"),
        "calibrator_sha256": _sha256(v4_dir / "platt-calibrator-v4.joblib"),
        "policy_sha256": _sha256(v4_dir / "policy-v4.json"),
    }
    if any(lock.get(key) != value for key, value in bindings.items()):
        raise ValueError("v4 candidate pre-evaluation lock mismatch")
    all_rows = _rows(features_path)
    candidate = [row for row in all_rows if row["split"] == "candidate_selection"]
    if len(candidate) != 1_500 or any(row["label_source"] == "weak_policy_v4" for row in candidate):
        raise ValueError("candidate selection is not the frozen reliable-label cohort")
    v4_manifest = json.loads((v4_dir / "catboost-v4.manifest.json").read_text())
    v4_model = CatBoostClassifier()
    v4_model.load_model(v4_dir / "catboost-v4.cbm")
    v4_raw = v4_model.predict_proba(
        [feature_vector_v3(row, v4_manifest["feature_names"]) for row in candidate]
    )[:, 1]
    v4_probabilities = _calibrated(load(v4_dir / "platt-calibrator-v4.joblib"), v4_raw)
    policy = json.loads((v4_dir / "policy-v4.json").read_text())
    predicted = _predicted(candidate, v4_probabilities, policy)
    policy_result = policy_metrics(
        candidate,
        v4_probabilities,
        float(policy["threshold"]),
        semantic_contradiction_threshold=policy.get("semantic_contradiction_threshold"),
        semantic_neutral_threshold=policy.get("semantic_neutral_threshold"),
    )
    labels = [int(row["expected_treatment"] != "APPROVE") for row in candidate]
    quality = _quality(labels, v4_probabilities)
    quality["expected_calibration_error"] = expected_calibration_error(labels, v4_probabilities)
    families = by_attack_family(candidate, predicted)
    reviewed_none_indexes = [
        index
        for index, row in enumerate(candidate)
        if row["attack_family"] == "none" and row["label_source"] == "llm_assisted_v4"
    ]
    reviewed_none_violations = [
        index for index in reviewed_none_indexes if candidate[index]["expected_treatment"] != "APPROVE"
    ]
    reviewed_none_recall = (
        sum(predicted[index] != "APPROVE" for index in reviewed_none_violations)
        / len(reviewed_none_violations)
        if reviewed_none_violations
        else 0.0
    )
    v3_manifest = json.loads(v3_manifest_path.read_text())
    v3_model = CatBoostClassifier()
    v3_model.load_model(v3_model_path)
    v3_raw = v3_model.predict_proba(
        [feature_vector_v2(row, v3_manifest["feature_names"]) for row in candidate]
    )[:, 1]
    v3_probability = _calibrated(load(v3_calibrator_path), v3_raw)
    v3_baseline = json.loads(v3_baseline_path.read_text())
    v3_policy = {
        **v3_baseline["candidates"]["calibrated_catboost"]["threshold_selection"],
        "semantic_contradiction_threshold": 0.8,
        "semantic_neutral_threshold": 0.6,
    }
    v3_predicted = _predicted(candidate, v3_probability, v3_policy)
    v3_quality = _quality(labels, v3_probability)
    v3_policy_result = policy_metrics(candidate, v3_probability, float(v3_policy["threshold"]))
    ledger = {row["example_id"]: row for row in _rows(selection_ledger_path)}
    challenge_indexes = [
        index
        for index, row in enumerate(candidate)
        if ledger.get(row["example_id"], {}).get("cohort") == "candidate_challenge"
    ]
    challenge = {
        "rows": len(challenge_indexes),
        "violation_recall": (
            sum(
                candidate[index]["expected_treatment"] != "APPROVE"
                and predicted[index] != "APPROVE"
                for index in challenge_indexes
            )
            / max(1, sum(candidate[index]["expected_treatment"] != "APPROVE" for index in challenge_indexes))
        ),
    }
    gates = gate_report(quality, policy_result, families, reviewed_none_recall, v3_quality["pr_auc"])
    report = {
        "evaluation_version": "development-v4-candidate-selection-v1",
        "status": "LOCKED_ELIGIBLE" if gates["all_passed"] else "LOCKED_NON_PROMOTABLE",
        "bindings": {**bindings, "candidate_pre_evaluation_lock_sha256": _sha256(lock_path)},
        "candidate_rows": len(candidate),
        "candidate_label_sources": dict(sorted(Counter(row["label_source"] for row in candidate).items())),
        "v4": {
            "quality": quality,
            "policy": policy_result,
            "by_attack_family": families,
            "reviewed_none_rows": len(reviewed_none_indexes),
            "reviewed_none_violation_rows": len(reviewed_none_violations),
            "reviewed_none_recall": reviewed_none_recall,
            "challenge": challenge,
        },
        "locked_v3_on_same_candidate": {
            "quality": v3_quality,
            "policy": v3_policy_result,
            "by_attack_family": by_attack_family(candidate, v3_predicted),
        },
        "gates": gates,
        "final_holdout_authorized": gates["all_passed"],
        "production_claim_eligible": False,
        "next_stage_paused_for_user_review": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--selection-ledger", type=Path, required=True)
    parser.add_argument("--v4-artifacts", type=Path, required=True)
    parser.add_argument("--v3-model", type=Path, required=True)
    parser.add_argument("--v3-manifest", type=Path, required=True)
    parser.add_argument("--v3-calibrator", type=Path, required=True)
    parser.add_argument("--v3-baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.features, args.selection_ledger, args.v4_artifacts, args.v3_model, args.v3_manifest, args.v3_calibrator, args.v3_baseline, args.output), indent=2))


if __name__ == "__main__":
    main()
