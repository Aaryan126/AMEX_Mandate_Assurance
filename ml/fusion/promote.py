from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def promote(manifest_path: Path, report_path: Path, output_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    report = json.loads(report_path.read_text())
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if report.get("status") != "passed":
        raise ValueError("only an artifact that passed the golden gate can be promoted")
    if report.get("model_version") != manifest.get("model_version"):
        raise ValueError("evaluation report model version does not match artifact")
    if report.get("dataset_sha256") != manifest.get("dataset_sha256"):
        raise ValueError("evaluation report dataset does not match artifact")
    if report.get("artifact_manifest_sha256") != manifest_sha256:
        raise ValueError("evaluation report is not bound to this artifact manifest")
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
