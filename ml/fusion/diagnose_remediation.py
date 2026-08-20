from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.evaluation.evaluate import _score_fusion, _validate_artifacts
from ml.fusion.policy_selection import (
    policy_metrics,
    select_policy_threshold,
    target_value,
)
from ml.tabular.train_catboost import load_rows

ALLOWED_SPLITS = {"train", "validation", "calibration"}


def shortcut_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["line_item_count"])].append(row)
    by_line_item_count = {}
    for count, values in sorted(grouped.items(), key=lambda item: int(item[0])):
        reviewed = [row for row in values if row.get("expected_treatment") is not None]
        interventions = sum(
            row["expected_treatment"] != "APPROVE" for row in reviewed
        )
        by_line_item_count[count] = {
            "rows": len(values),
            "reviewed_rows": len(reviewed),
            "intervention_rate": interventions / len(reviewed) if reviewed else None,
            "attack_families": dict(
                sorted(Counter(str(row.get("attack_family")) for row in values).items())
            ),
        }
    unrelated = [row for row in rows if row.get("attack_family") == "unrelated_add_on"]
    multi_item = [row for row in rows if int(row["line_item_count"]) > 1]
    return {
        "by_line_item_count": by_line_item_count,
        "unrelated_add_on_rows": len(unrelated),
        "unrelated_add_on_multi_item_fraction": (
            sum(int(row["line_item_count"]) > 1 for row in unrelated) / len(unrelated)
            if unrelated
            else None
        ),
        "multi_item_rows": len(multi_item),
        "multi_item_unrelated_add_on_fraction": (
            sum(row.get("attack_family") == "unrelated_add_on" for row in multi_item)
            / len(multi_item)
            if multi_item
            else None
        ),
    }


def _target_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for split in sorted(ALLOWED_SPLITS):
        values = [row for row in rows if row["split"] == split]
        result[split] = {
            "rows": len(values),
            "binary_deviation_rows": sum(
                target_value(row, "binary_deviation") is not None for row in values
            ),
            "policy_intervention_rows": sum(
                target_value(row, "policy_intervention") is not None for row in values
            ),
            "ambiguous_step_up_rows": sum(
                row.get("label") is None
                and row.get("expected_treatment") == "STEP_UP"
                for row in values
            ),
        }
    return result


def diagnose(dataset_path: Path, artifact_dir: Path, output_path: Path) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before diagnosing fusion") from exc

    all_rows = load_rows(dataset_path)
    manifest, feature_manifest = _validate_artifacts(
        dataset_path, artifact_dir, all_rows
    )
    split_counts = Counter(str(row["split"]) for row in all_rows)
    rows = [row for row in all_rows if row["split"] in ALLOWED_SPLITS]
    if not rows or any(row["split"] == "golden" for row in rows):
        raise ValueError("remediation diagnosis must contain only non-golden rows")

    base_model = CatBoostClassifier()
    base_model.load_model(artifact_dir / manifest["base_artifact"])
    bundle = json.loads((artifact_dir / manifest["fusion_artifact"]).read_text())
    feature_names = [str(value) for value in manifest["feature_names"]]
    stack_features = [str(value) for value in manifest["stack_features"]]
    scored: dict[str, dict[str, Any]] = {}
    validation_rows: list[dict[str, Any]] = []
    validation_probabilities: list[float] = []
    for split in ("validation", "calibration"):
        split_rows = [
            row
            for row in rows
            if row["split"] == split and row.get("expected_treatment") is not None
        ]
        _, _, probabilities = _score_fusion(
            split_rows, base_model, bundle, feature_names, stack_features
        )
        scored[split] = {
            "current_threshold": policy_metrics(
                split_rows,
                probabilities,
                float(manifest["model_step_up_threshold"]),
            ),
            "fixed_overrides_only": policy_metrics(
                split_rows, probabilities, math.nextafter(1.0, math.inf)
            ),
        }
        if split == "validation":
            validation_rows = split_rows
            validation_probabilities = probabilities

    try:
        selection: dict[str, Any] = {
            "status": "feasible",
            **select_policy_threshold(
                validation_rows,
                validation_probabilities,
                float(manifest["false_step_up_target"]),
            ),
        }
    except ValueError as exc:
        selection = {"status": "infeasible", "reason": str(exc)}

    report = {
        "schema_version": "fast-track-remediation-diagnosis-v1",
        "status": "diagnosed",
        "scope": "train/validation/calibration only",
        "golden_rows_scored": 0,
        "excluded_split_counts": {
            split: count
            for split, count in sorted(split_counts.items())
            if split not in ALLOWED_SPLITS
        },
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "feature_manifest_sha256": feature_manifest["manifest_sha256"],
        "artifact_manifest_sha256": hashlib.sha256(
            (artifact_dir / "fusion-v2.manifest.json").read_bytes()
        ).hexdigest(),
        "current_model": {
            "model_version": manifest["model_version"],
            "feature_profile": manifest.get("feature_profile", "full-v2"),
            "target_mode": manifest.get("target_mode", "binary_deviation"),
            "threshold_selection_method": manifest.get(
                "threshold_selection_method", "probability-only-binary-v0"
            ),
            "threshold": manifest["model_step_up_threshold"],
        },
        "target_coverage": _target_coverage(rows),
        "policy_metrics": scored,
        "policy_aware_validation_selection": selection,
        "shortcut_analysis": shortcut_summary(rows),
        "approved_candidate_contracts": [
            {
                "name": "structured_no_semantic",
                "feature_profile": "shortcut-safe-no-semantic-v2",
                "target_mode": "policy_intervention",
                "purpose": "structured baseline without semantic scores or line-item shortcut",
            },
            {
                "name": "structured_with_semantic",
                "feature_profile": "shortcut-safe-v2",
                "target_mode": "policy_intervention",
                "purpose": "test semantic contribution without line-item shortcut",
            },
        ],
        "constraints": [
            "Do not tune against the original golden split.",
            "Threshold selection must measure the complete deterministic and model policy.",
            "Model-only HOLD remains disabled.",
            "Only declared feature profiles may be loaded by the API.",
        ],
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
        default=Path("artifacts/models/fast-track-fusion-v2"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/step20-remediation-diagnosis.json"),
    )
    args = parser.parse_args()
    print(json.dumps(diagnose(args.dataset, args.artifacts, args.output), indent=2))


if __name__ == "__main__":
    main()
