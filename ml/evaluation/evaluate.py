from __future__ import annotations

import argparse
import json
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml.evaluation.metrics import (
    by_attack_family,
    expected_calibration_error,
    treatment_metrics,
)
from ml.features.schema import feature_vector
from ml.fusion.train_fusion import _stack_row
from ml.tabular.train_catboost import load_rows


def predict_treatment(
    row: dict[str, Any], probability: float, approve_threshold: float, decline_threshold: float
) -> str:
    family = row["attack_family"]
    if family in {"unrelated_add_on", "cumulative_overspend", "semantic_substitution"}:
        return "HOLD"
    if family == "missing_evidence" or row["hard_fail_count"]:
        return "STEP_UP"
    if probability < approve_threshold:
        return "APPROVE"
    if probability < decline_threshold:
        return "STEP_UP"
    return "HOLD"


def evaluate(dataset_path: Path, artifact_dir: Path, output_path: Path) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
        from sklearn.metrics import (
            average_precision_score,
            precision_score,
            recall_score,
        )
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before running evaluation") from exc

    rows = load_rows(dataset_path)
    golden = [row for row in rows if row["split"] == "golden"]
    base_model = CatBoostClassifier()
    base_model.load_model(artifact_dir / "fusion-catboost-v1.cbm")
    bundle = pickle.loads((artifact_dir / "stacker-calibrator-v1.pkl").read_bytes())
    manifest = json.loads((artifact_dir / "stacker-calibrator-v1.manifest.json").read_text())

    start = time.perf_counter()
    base_probabilities = base_model.predict_proba([feature_vector(row) for row in golden])[:, 1]
    stack_probabilities = bundle["stacker"].predict_proba(
        [_stack_row(row, value) for row, value in zip(golden, base_probabilities, strict=True)]
    )[:, 1]
    probabilities = bundle["calibrator"].predict_proba(
        [[float(value)] for value in stack_probabilities]
    )[:, 1]
    elapsed_ms = (time.perf_counter() - start) * 1000
    treatments = [
        predict_treatment(
            row,
            float(probability),
            float(manifest["approve_threshold"]),
            float(manifest["decline_threshold"]),
        )
        for row, probability in zip(golden, probabilities, strict=True)
    ]

    labeled_positions = [index for index, row in enumerate(golden) if row["label"] is not None]
    labels = [int(golden[index]["label"]) for index in labeled_positions]
    labeled_probabilities = [float(probabilities[index]) for index in labeled_positions]
    binary_predictions = [int(value >= 0.5) for value in labeled_probabilities]
    metrics = treatment_metrics(
        [row["expected_treatment"] for row in golden],
        treatments,
    )
    metrics.update(
        {
            "binary_violation_recall": float(recall_score(labels, binary_predictions)),
            "high_risk_precision": float(precision_score(labels, binary_predictions, zero_division=0)),
            "pr_auc": float(average_precision_score(labels, labeled_probabilities)),
            "expected_calibration_error": expected_calibration_error(labels, labeled_probabilities),
        }
    )
    report = {
        "dataset_version": "synthetic-v1",
        "model_version": "stacker-calibrator-v1",
        "status": "passed"
        if metrics["violation_recall"] >= 0.90
        and metrics["false_step_up_rate"] <= 0.10
        and metrics["false_decline_rate"] <= 0.02
        else "failed_gate",
        "metrics": metrics,
        "attack_families": by_attack_family(golden, treatments),
        "latency_ms": {"p50": elapsed_ms / max(len(golden), 1), "p95": elapsed_ms},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("ml/data/generated/mandate-cart-pairs.jsonl"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/models"))
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/reports/evaluation-summary.json")
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, args.artifacts, args.output), indent=2))


if __name__ == "__main__":
    main()
