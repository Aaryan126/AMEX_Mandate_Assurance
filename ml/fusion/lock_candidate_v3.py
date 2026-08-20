from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

GATES = {
    "operational_recall_min": 0.90,
    "false_step_up_max": 0.10,
    "false_decline_max": 0.02,
    "expected_calibration_error_max": 0.08,
    "supported_family_recall_min": 0.80,
    "supported_family_min_violations": 50,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_gates(report: dict[str, Any]) -> dict[str, Any]:
    selected_name = report["selected_candidate"]
    selected = report["candidates"][selected_name]
    policy = selected["candidate_selection_policy"]
    quality = selected["candidate_selection_quality"]
    supported = {
        family: metrics
        for family, metrics in selected["by_attack_family"].items()
        if metrics["violation_rows"] >= GATES["supported_family_min_violations"]
    }
    family_failures = {
        family: metrics["violation_recall"]
        for family, metrics in supported.items()
        if metrics["violation_recall"] < GATES["supported_family_recall_min"]
    }
    checks = {
        "operational_recall": {
            "value": policy["violation_recall"],
            "threshold": GATES["operational_recall_min"],
            "passed": policy["violation_recall"] >= GATES["operational_recall_min"],
        },
        "false_step_up": {
            "value": policy["false_step_up_rate"],
            "threshold": GATES["false_step_up_max"],
            "passed": policy["false_step_up_rate"] <= GATES["false_step_up_max"],
        },
        "false_decline": {
            "value": policy["false_decline_rate"],
            "threshold": GATES["false_decline_max"],
            "passed": policy["false_decline_rate"] <= GATES["false_decline_max"],
        },
        "calibration": {
            "value": quality["expected_calibration_error"],
            "threshold": GATES["expected_calibration_error_max"],
            "passed": quality["expected_calibration_error"]
            <= GATES["expected_calibration_error_max"],
        },
        "supported_families": {
            "supported": sorted(supported),
            "failures": family_failures,
            "threshold": GATES["supported_family_recall_min"],
            "passed": not family_failures,
        },
    }
    return {
        "selected_candidate": selected_name,
        "checks": checks,
        "all_passed": all(check["passed"] for check in checks.values()),
    }


def lock(
    baseline_report_path: Path,
    dataset_manifest_path: Path,
    catboost_model_path: Path,
    catboost_manifest_path: Path,
    calibrator_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    baseline = json.loads(baseline_report_path.read_text())
    gates = evaluate_gates(baseline)
    selected = baseline["candidates"][gates["selected_candidate"]]
    lock_data = {
        "lock_version": "candidate-lock-v3",
        "status": "LOCKED_ELIGIBLE" if gates["all_passed"] else "LOCKED_NON_PROMOTABLE",
        "selected_candidate": gates["selected_candidate"],
        "policy_threshold": selected["threshold_selection"]["threshold"],
        "gates": gates,
        "bindings": {
            "baseline_report": str(baseline_report_path),
            "baseline_report_sha256": _sha256(baseline_report_path),
            "dataset_manifest": str(dataset_manifest_path),
            "dataset_manifest_sha256": _sha256(dataset_manifest_path),
            "catboost_model": str(catboost_model_path),
            "catboost_model_sha256": _sha256(catboost_model_path),
            "catboost_manifest": str(catboost_manifest_path),
            "catboost_manifest_sha256": _sha256(catboost_manifest_path),
            "calibrator": str(calibrator_path),
            "calibrator_sha256": _sha256(calibrator_path),
        },
        "final_holdout_authorized": gates["all_passed"],
        "production_claim_eligible": False,
        "human_validation_missing": True,
        "decision": (
            "Freeze a new final holdout only after every development gate passes."
            if gates["all_passed"]
            else "Do not freeze or review a new final holdout; remediate on development data."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(lock_data, indent=2, sort_keys=True) + "\n")
    return lock_data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--catboost-model", type=Path, required=True)
    parser.add_argument("--catboost-manifest", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            lock(
                args.baseline_report,
                args.dataset_manifest,
                args.catboost_model,
                args.catboost_manifest,
                args.calibrator,
                args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
