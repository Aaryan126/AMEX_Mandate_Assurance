from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.evaluation.evaluate import _score_fusion, _validate_artifacts
from ml.fusion.policy_selection import policy_metrics
from ml.tabular.train_catboost import load_rows

FALSE_DECLINE_LIMIT = 0.02
CANDIDATE_PROFILES = {
    "no-semantic": "shortcut-safe-no-semantic-v2",
    "with-semantic": "shortcut-safe-v2",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_eligibility(
    metrics: dict[str, Any], false_step_up_limit: float
) -> dict[str, Any]:
    criteria = {
        "false_step_up_rate": {
            "actual": float(metrics["false_step_up_rate"]),
            "operator": "<=",
            "limit": false_step_up_limit,
        },
        "false_decline_rate": {
            "actual": float(metrics["false_decline_rate"]),
            "operator": "<=",
            "limit": FALSE_DECLINE_LIMIT,
        },
    }
    for criterion in criteria.values():
        criterion["passed"] = criterion["actual"] <= criterion["limit"] + 1e-12
    return {
        "eligible": all(value["passed"] for value in criteria.values()),
        "criteria": criteria,
    }


def choose_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose the highest-recall eligible candidate with deterministic tie-breaks."""
    eligible = [candidate for candidate in candidates if candidate["eligibility"]["eligible"]]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda candidate: (
            -float(candidate["validation_policy_metrics"]["violation_recall"]),
            float(candidate["validation_policy_metrics"]["false_step_up_rate"]),
            float(candidate["validation_policy_metrics"]["false_decline_rate"]),
            str(candidate["name"]),
        ),
    )


def _validate_candidate_contract(
    name: str, manifest: dict[str, Any], validation_rows: int
) -> None:
    expected_profile = CANDIDATE_PROFILES[name]
    requirements = {
        "feature_profile": expected_profile,
        "target_mode": "policy_intervention",
        "threshold_selection_method": "complete-policy-validation-v1",
        "model_hold_enabled": False,
        "serving_approved": False,
        "threshold_selection_rows": validation_rows,
    }
    for field, expected in requirements.items():
        if manifest.get(field) != expected:
            raise ValueError(
                f"{name} candidate has invalid {field}: "
                f"expected {expected!r}, found {manifest.get(field)!r}"
            )
    false_step_up_target = manifest.get("false_step_up_target")
    if not isinstance(false_step_up_target, (int, float)) or not (
        0 <= float(false_step_up_target) < 1
    ):
        raise ValueError(f"{name} candidate has an invalid false-step-up target")
    threshold = manifest.get("model_step_up_threshold")
    if not isinstance(threshold, (int, float)) or not (0 <= float(threshold) <= 1):
        raise ValueError(f"{name} candidate has an invalid operating threshold")


def select_remediation_candidate(
    dataset_path: Path, artifact_root: Path, output_path: Path
) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before selecting fusion") from exc

    all_rows = load_rows(dataset_path)
    split_counts = Counter(str(row["split"]) for row in all_rows)
    validation = [
        row
        for row in all_rows
        if row["split"] == "validation"
        and row.get("expected_treatment") in {"APPROVE", "STEP_UP", "HOLD"}
    ]
    if not validation:
        raise ValueError("candidate selection requires reviewed validation rows")

    candidates: list[dict[str, Any]] = []
    feature_manifest_sha256: str | None = None
    for name in CANDIDATE_PROFILES:
        artifact_dir = artifact_root / name
        manifest, feature_manifest = _validate_artifacts(
            dataset_path, artifact_dir, all_rows
        )
        _validate_candidate_contract(name, manifest, len(validation))
        current_feature_manifest_sha256 = str(feature_manifest["manifest_sha256"])
        if feature_manifest_sha256 not in {None, current_feature_manifest_sha256}:
            raise ValueError("candidate feature manifests do not match")
        feature_manifest_sha256 = current_feature_manifest_sha256

        model = CatBoostClassifier()
        model.load_model(artifact_dir / manifest["base_artifact"])
        bundle = json.loads((artifact_dir / manifest["fusion_artifact"]).read_text())
        _, _, probabilities = _score_fusion(
            validation,
            model,
            bundle,
            [str(value) for value in manifest["feature_names"]],
            [str(value) for value in manifest["stack_features"]],
        )
        metrics = policy_metrics(
            validation, probabilities, float(manifest["model_step_up_threshold"])
        )
        recorded_metrics = manifest.get("threshold_selection_metrics", {})
        for field in ("false_step_up_rate", "false_decline_rate", "violation_recall"):
            if abs(float(metrics[field]) - float(recorded_metrics.get(field, -1))) > 1e-12:
                raise ValueError(f"{name} recomputed {field} does not match its manifest")

        manifest_path = artifact_dir / "fusion-v2.manifest.json"
        candidates.append(
            {
                "name": name,
                "artifact_dir": str(artifact_dir),
                "artifact_manifest_sha256": _sha256(manifest_path),
                "feature_profile": manifest["feature_profile"],
                "target_mode": manifest["target_mode"],
                "threshold_selection_method": manifest["threshold_selection_method"],
                "model_step_up_threshold": manifest["model_step_up_threshold"],
                "validation_policy_metrics": metrics,
                "eligibility": _candidate_eligibility(
                    metrics, float(manifest["false_step_up_target"])
                ),
            }
        )

    selected = choose_candidate(candidates)
    report = {
        "schema_version": "fast-track-remediation-selection-v1",
        "status": "selected" if selected is not None else "no_eligible_candidate",
        "selection_basis": (
            "highest validation intervention recall among candidates satisfying the "
            "complete-policy false-step-up and false-decline limits"
        ),
        "scope": "reviewed validation rows only",
        "scored_splits": ["validation"],
        "validation_rows_scored": len(validation),
        "calibration_rows_scored": 0,
        "golden_rows_scored": 0,
        "replacement_holdout_rows_scored": 0,
        "split_counts_present_but_not_scored": {
            split: count
            for split, count in sorted(split_counts.items())
            if split != "validation"
        },
        "dataset_sha256": _sha256(dataset_path),
        "feature_manifest_sha256": feature_manifest_sha256,
        "candidate_contract": {
            "target_mode": "policy_intervention",
            "threshold_selection_method": "complete-policy-validation-v1",
            "model_only_hold_enabled": False,
            "serving_approved": False,
            "false_decline_limit": FALSE_DECLINE_LIMIT,
        },
        "candidates": candidates,
        "selected_candidate": (
            {
                "name": selected["name"],
                "artifact_dir": selected["artifact_dir"],
                "artifact_manifest_sha256": selected["artifact_manifest_sha256"],
                "feature_profile": selected["feature_profile"],
            }
            if selected is not None
            else None
        ),
        "note": (
            "The calibration split fitted the Platt calibrator and is intentionally not "
            "reused for candidate selection. The replacement holdout remains sealed for Step 23."
        ),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f"{output_path.name}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(output_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("ml/data/generated/fast-track/features-v2.jsonl"),
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("artifacts/models/fast-track-remediation-v3"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/step22-remediation-selection.json"),
    )
    args = parser.parse_args()
    report = select_remediation_candidate(args.dataset, args.artifacts, args.output)
    print(json.dumps(report, indent=2))
    if report["status"] != "selected":
        raise SystemExit("no remediation candidate passed the selection constraints")


if __name__ == "__main__":
    main()
