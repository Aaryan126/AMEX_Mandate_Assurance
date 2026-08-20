from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from joblib import load

from ml.evaluation.evaluate_v4 import GATES, gate_report
from ml.evaluation.metrics import by_attack_family, expected_calibration_error
from ml.features.schema import feature_vector as feature_vector_v2
from ml.features.schema_v3 import feature_vector as feature_vector_v3
from ml.fusion.baselines_v3 import _quality
from ml.fusion.policy_selection import policy_metrics, predict_policy_treatment


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def _calibrated(calibrator: Any, values: Any) -> list[float]:
    logits = [[math.log(value / (1 - value))] for raw in values for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]]
    return [float(value) for value in calibrator.predict_proba(logits)[:, 1]]


def _predicted(rows: list[dict[str, Any]], probabilities: list[float], policy: dict[str, Any]) -> list[str]:
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


def _policy_result(rows: list[dict[str, Any]], probabilities: list[float], policy: dict[str, Any]) -> dict[str, Any]:
    return policy_metrics(
        rows,
        probabilities,
        float(policy["threshold"]),
        semantic_contradiction_threshold=policy.get("semantic_contradiction_threshold"),
        semantic_neutral_threshold=policy.get("semantic_neutral_threshold"),
    )


def evaluate(
    features_path: Path,
    selection_ledger_path: Path,
    artifacts_dir: Path,
    v3_model_path: Path,
    v3_manifest_path: Path,
    v3_calibrator_path: Path,
    v3_baseline_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    from catboost import CatBoostClassifier

    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite Stage B candidate evaluation: {output_path}")
    manifest_path = artifacts_dir / "manifest.json"
    lock_path = artifacts_dir / "candidate-pre-evaluation-lock.json"
    manifest = json.loads(manifest_path.read_text())
    lock = json.loads(lock_path.read_text())
    if lock.get("features_sha256") != _sha256(features_path) or lock.get("manifest_sha256") != _sha256(manifest_path):
        raise ValueError("Stage B candidate lock mismatch")
    if lock.get("status") != "FROZEN_UNEVALUATED" or lock.get("candidate_rows_accessed") != 0:
        raise ValueError("Stage B candidate was not cleanly frozen")
    candidate = [row for row in _rows(features_path) if row["split"] == "candidate_selection"]
    if len(candidate) != 1_400 or Counter(row["label_source"] for row in candidate) != Counter({"deterministic_policy_v4": 1_000, "llm_assisted_v4": 400}):
        raise ValueError("Stage B candidate is not the frozen reliable-label cohort")

    v3_manifest = json.loads(v3_manifest_path.read_text())
    v3_model = CatBoostClassifier()
    v3_model.load_model(v3_model_path)
    v3_raw = v3_model.predict_proba([feature_vector_v2(row, v3_manifest["feature_names"]) for row in candidate])[:, 1]
    v3_probability = _calibrated(load(v3_calibrator_path), v3_raw)
    if manifest["selected_candidate"] == "locked_v3_routed":
        probability = v3_probability
        policy_path = artifacts_dir / "policy-locked-v3-routed.json"
    elif manifest["selected_candidate"] == "retrained_v3_semantic_v4":
        model = CatBoostClassifier()
        model.load_model(artifacts_dir / "catboost-stage-b.cbm")
        raw = model.predict_proba([feature_vector_v3(row, manifest["retrained_feature_names"]) for row in candidate])[:, 1]
        probability = _calibrated(load(artifacts_dir / "platt-stage-b.joblib"), raw)
        policy_path = artifacts_dir / "policy-retrained.json"
    else:
        raise ValueError("unknown frozen Stage B candidate")
    policy = json.loads(policy_path.read_text())
    predicted = _predicted(candidate, probability, policy)
    labels = [int(row["expected_treatment"] != "APPROVE") for row in candidate]
    quality = _quality(labels, probability)
    quality["expected_calibration_error"] = expected_calibration_error(labels, probability)
    policy_result = _policy_result(candidate, probability, policy)
    families = by_attack_family(candidate, predicted)

    reviewed_indexes = [index for index, row in enumerate(candidate) if row["label_source"] == "llm_assisted_v4"]
    reviewed_violations = [index for index in reviewed_indexes if candidate[index]["expected_treatment"] != "APPROVE"]
    reviewed_recall = sum(predicted[index] != "APPROVE" for index in reviewed_violations) / max(1, len(reviewed_violations))
    ledger = {row["example_id"]: row for row in _rows(selection_ledger_path)}
    challenge_indexes = [index for index in reviewed_indexes if ledger.get(candidate[index]["example_id"], {}).get("cohort") == "challenge"]
    challenge_violations = [index for index in challenge_indexes if candidate[index]["expected_treatment"] != "APPROVE"]
    challenge_recall = sum(predicted[index] != "APPROVE" for index in challenge_violations) / max(1, len(challenge_violations))

    baseline = json.loads(v3_baseline_path.read_text())
    baseline_policy = {
        **baseline["candidates"]["calibrated_catboost"]["threshold_selection"],
        "semantic_contradiction_threshold": 0.8,
        "semantic_neutral_threshold": 0.6,
    }
    baseline_predicted = _predicted(candidate, v3_probability, baseline_policy)
    baseline_quality = _quality(labels, v3_probability)
    baseline_quality["expected_calibration_error"] = expected_calibration_error(labels, v3_probability)
    baseline_policy_result = _policy_result(candidate, v3_probability, baseline_policy)
    gates = gate_report(quality, policy_result, families, reviewed_recall, baseline_quality["pr_auc"])
    report = {
        "evaluation_version": "development-v4-semantic-stage-b-candidate-v1",
        "status": "LOCKED_ELIGIBLE" if gates["all_passed"] else "LOCKED_NON_PROMOTABLE",
        "selected_candidate": manifest["selected_candidate"],
        "bindings": {
            "features_sha256": _sha256(features_path),
            "manifest_sha256": _sha256(manifest_path),
            "candidate_pre_evaluation_lock_sha256": _sha256(lock_path),
            "policy_sha256": _sha256(policy_path),
        },
        "candidate_rows": len(candidate),
        "candidate_label_sources": dict(sorted(Counter(row["label_source"] for row in candidate).items())),
        "stage_b": {
            "quality": quality,
            "policy": policy_result,
            "by_attack_family": families,
            "reviewed_semantic_rows": len(reviewed_indexes),
            "reviewed_semantic_violation_rows": len(reviewed_violations),
            "reviewed_semantic_recall": reviewed_recall,
            "challenge_rows": len(challenge_indexes),
            "challenge_violation_rows": len(challenge_violations),
            "challenge_recall": challenge_recall,
        },
        "locked_v3_original_policy_on_same_candidate": {
            "quality": baseline_quality,
            "policy": baseline_policy_result,
            "by_attack_family": by_attack_family(candidate, baseline_predicted),
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
    parser = argparse.ArgumentParser(description="Evaluate the frozen Stage B candidate once")
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--selection-ledger", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--v3-model", type=Path, required=True)
    parser.add_argument("--v3-manifest", type=Path, required=True)
    parser.add_argument("--v3-calibrator", type=Path, required=True)
    parser.add_argument("--v3-baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.features, args.selection_ledger, args.artifacts, args.v3_model, args.v3_manifest, args.v3_calibrator, args.v3_baseline, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
