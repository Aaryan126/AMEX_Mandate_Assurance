from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.evaluation.metrics import (
    by_attack_family,
    expected_calibration_error,
    treatment_metrics,
)
from ml.features.schema import feature_vector
from ml.fusion.train_fusion import _stack_row, logistic_probability
from ml.tabular.train_catboost import load_rows


def predict_treatment(
    row: dict[str, Any], probability: float, model_step_up_threshold: float
) -> str:
    """Mirror live policy using observable evidence only; attack_family is evaluation metadata."""
    if row.get("critical_hold_count", 0):
        return "HOLD"
    if (
        row["hard_fail_count"]
        or row["semantic_contradiction"] >= 0.8
        or row["semantic_neutral"] >= 0.6
        or probability >= model_step_up_threshold
    ):
        return "STEP_UP"
    return "APPROVE"


def evaluate(
    dataset_path: Path, artifact_dir: Path, output_path: Path
) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
        from sklearn.metrics import (
            average_precision_score,
            precision_score,
            recall_score,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Install services/api[ml] before running evaluation"
        ) from exc

    rows = load_rows(dataset_path)
    golden = [row for row in rows if row["split"] == "golden"]
    if not golden:
        raise ValueError("evaluation requires a non-empty golden split")
    manifest = json.loads((artifact_dir / "fusion-v2.manifest.json").read_text())
    base_model = CatBoostClassifier()
    base_model.load_model(artifact_dir / manifest["base_artifact"])
    bundle = json.loads((artifact_dir / manifest["fusion_artifact"]).read_text())

    start = time.perf_counter()
    base_probabilities = base_model.predict_proba(
        [feature_vector(row) for row in golden]
    )[:, 1]
    stack_probabilities = [
        logistic_probability(bundle["stacker"], _stack_row(row, float(value)))
        for row, value in zip(golden, base_probabilities, strict=True)
    ]
    probabilities = [
        logistic_probability(bundle["calibrator"], [float(value)])
        for value in stack_probabilities
    ]
    elapsed_ms = (time.perf_counter() - start) * 1000
    treatments = [
        predict_treatment(
            row,
            probability,
            float(manifest["model_step_up_threshold"]),
        )
        for row, probability in zip(golden, probabilities, strict=True)
    ]

    labeled_positions = [
        index for index, row in enumerate(golden) if row["label"] is not None
    ]
    treatment_positions = [
        index
        for index, row in enumerate(golden)
        if row["expected_treatment"] is not None
    ]
    if not labeled_positions or not treatment_positions:
        raise ValueError("golden split requires resolved binary and treatment labels")
    labels = [int(golden[index]["label"]) for index in labeled_positions]
    labeled_probabilities = [probabilities[index] for index in labeled_positions]
    binary_predictions = [int(value >= 0.5) for value in labeled_probabilities]
    metrics = treatment_metrics(
        [golden[index]["expected_treatment"] for index in treatment_positions],
        [treatments[index] for index in treatment_positions],
    )
    metrics.update(
        {
            "binary_violation_recall": float(recall_score(labels, binary_predictions)),
            "high_risk_precision": float(
                precision_score(labels, binary_predictions, zero_division=0)
            ),
            "pr_auc": float(average_precision_score(labels, labeled_probabilities)),
            "expected_calibration_error": expected_calibration_error(
                labels, labeled_probabilities
            ),
        }
    )
    report = {
        "dataset_version": manifest["dataset_version"],
        "model_version": manifest["model_version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "artifact_manifest_sha256": hashlib.sha256(
            (artifact_dir / "fusion-v2.manifest.json").read_bytes()
        ).hexdigest(),
        "status": (
            "passed"
            if metrics["violation_recall"] >= 0.90
            and metrics["false_step_up_rate"] <= 0.10
            and metrics["false_decline_rate"] <= 0.02
            else "failed_gate"
        ),
        "metrics": metrics,
        "attack_families": by_attack_family(
            [golden[index] for index in treatment_positions],
            [treatments[index] for index in treatment_positions],
        ),
        "latency_ms": {
            "p50": elapsed_ms / max(len(golden), 1),
            "p95": elapsed_ms,
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("ml/data/generated/features-v2.jsonl"),
    )
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/models"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/evaluation-summary.json"),
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, args.artifacts, args.output), indent=2))


if __name__ == "__main__":
    main()
