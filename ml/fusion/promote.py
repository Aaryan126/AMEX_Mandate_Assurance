from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from ml.features.schema import feature_profile_for_names


def promote(manifest_path: Path, report_path: Path, output_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    report = json.loads(report_path.read_text())
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if report.get("status") != "passed":
        raise ValueError("only an artifact that passed the golden gate can be promoted")
    if report.get("schema_version") != "golden-evaluation-v2":
        raise ValueError("promotion requires a versioned golden evaluation report")
    if report.get("evaluation_split") != "golden":
        raise ValueError("promotion requires evaluation on the golden split")
    gate = report.get("gate", {})
    criteria = gate.get("criteria", {}) if isinstance(gate, dict) else {}
    if gate.get("status") != "passed" or not criteria:
        raise ValueError("evaluation report does not contain a passed promotion gate")
    if any(value.get("passed") is not True for value in criteria.values()):
        raise ValueError("evaluation report contains a failed promotion criterion")
    if report.get("model_version") != manifest.get("model_version"):
        raise ValueError("evaluation report model version does not match artifact")
    if report.get("dataset_sha256") != manifest.get("dataset_sha256"):
        raise ValueError("evaluation report dataset does not match artifact")
    if report.get("artifact_manifest_sha256") != manifest_sha256:
        raise ValueError("evaluation report is not bound to this artifact manifest")
    try:
        feature_profile = feature_profile_for_names(manifest.get("feature_names", []))
    except ValueError as exc:
        raise ValueError("fusion artifact does not use a declared feature profile") from exc
    if manifest.get("feature_profile") != feature_profile:
        raise ValueError("fusion artifact feature profile is inconsistent")
    if feature_profile not in {
        "shortcut-safe-v2",
        "shortcut-safe-no-semantic-v2",
    }:
        raise ValueError("fusion artifact still contains the line-item shortcut feature")
    if manifest.get("target_mode") != "policy_intervention":
        raise ValueError("fusion artifact was not trained for the policy-intervention target")
    if manifest.get("threshold_selection_method") != "complete-policy-validation-v1":
        raise ValueError("fusion threshold was not selected against the complete policy")
    if report.get("integrity_checks", {}).get("feature_profile") != feature_profile:
        raise ValueError("evaluation report feature profile does not match the artifact")
    if manifest.get("model_hold_enabled"):
        raise ValueError("this API policy prohibits promotion of model-only HOLD")
    if str(manifest.get("dataset_version", "")).startswith("synthetic"):
        raise ValueError("synthetic smoke-test artifacts cannot be promoted")
    semantic_versions = manifest.get("semantic_model_versions", [])
    if not semantic_versions or "unknown" in semantic_versions:
        raise ValueError("fusion artifact is not bound to a versioned semantic model")
    promoted = {
        **manifest,
        "serving_approved": True,
        "promotion": {
            "evaluation_report_sha256": hashlib.sha256(
                report_path.read_bytes()
            ).hexdigest(),
            "promoted_at": datetime.now(UTC).isoformat(),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(promoted, indent=2, sort_keys=True) + "\n")
    return promoted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("artifacts/models/fusion-v2.manifest.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/reports/evaluation-summary.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/models/fusion-v2.serving.manifest.json"),
    )
    args = parser.parse_args()
    print(json.dumps(promote(args.manifest, args.report, args.output), indent=2))


if __name__ == "__main__":
    main()
