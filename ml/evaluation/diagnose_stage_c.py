from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from joblib import load

from ml.data.schema import AceDatasetExample
from ml.features.schema import feature_vector
from ml.fusion.policy_selection import predict_policy_treatment

ORACLE_SEMANTIC_RECALL_PROCEED = 0.65
OPERATIONAL_RECALL_MIN = 0.90
FALSE_STEP_UP_MAX = 0.10
REVIEWED_VIOLATIONS_MIN = 100
SEMANTIC_TARGET = 0.80


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def _calibrated(calibrator: Any, values: Any) -> list[float]:
    logits = [
        [math.log(value / (1 - value))]
        for raw in values
        for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]
    ]
    return [float(value) for value in calibrator.predict_proba(logits)[:, 1]]


def oracle_routing(
    rows: list[dict[str, Any]], probabilities: list[float]
) -> dict[str, Any]:
    """Measure optimistic routing headroom on an already-consumed cohort.

    This is a failure-analysis diagnostic, never a policy-selection result. The grid is
    deliberately fixed so repeated executions cannot silently optimize a larger search.
    """
    if len(rows) != len(probabilities) or not rows:
        raise ValueError("oracle routing requires aligned, non-empty rows")
    legitimate = [index for index, row in enumerate(rows) if row["expected_treatment"] == "APPROVE"]
    violations = [index for index, row in enumerate(rows) if row["expected_treatment"] != "APPROVE"]
    reviewed_violations = [
        index
        for index in violations
        if row_label_source(rows[index]) == "llm_assisted_v4"
    ]
    if not legitimate or not violations or not reviewed_violations:
        raise ValueError("oracle routing requires legitimate, violation, and reviewed-violation rows")
    best: tuple[tuple[float, float, float, float], dict[str, Any]] | None = None
    semantic_thresholds: tuple[float | None, ...] = (
        None,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
        0.95,
        1.00,
    )
    for score_index in range(0, 201):
        score_threshold = score_index / 200
        for contradiction_threshold in semantic_thresholds:
            for neutral_threshold in semantic_thresholds:
                predicted = [
                    predict_policy_treatment(
                        row,
                        probability,
                        score_threshold,
                        semantic_contradiction_threshold=contradiction_threshold,
                        semantic_neutral_threshold=neutral_threshold,
                    )
                    != "APPROVE"
                    for row, probability in zip(rows, probabilities, strict=True)
                ]
                false_step_up = sum(predicted[index] for index in legitimate) / len(legitimate)
                operational_recall = sum(predicted[index] for index in violations) / len(violations)
                if false_step_up > FALSE_STEP_UP_MAX or operational_recall < OPERATIONAL_RECALL_MIN:
                    continue
                semantic_recall = sum(predicted[index] for index in reviewed_violations) / len(reviewed_violations)
                rank = (
                    semantic_recall,
                    operational_recall,
                    -false_step_up,
                    score_threshold,
                )
                value = {
                    "semantic_recall": semantic_recall,
                    "operational_recall": operational_recall,
                    "false_step_up_rate": false_step_up,
                    "score_threshold": score_threshold,
                    "semantic_contradiction_threshold": contradiction_threshold,
                    "semantic_neutral_threshold": neutral_threshold,
                }
                if best is None or rank > best[0]:
                    best = (rank, value)
    if best is None:
        raise ValueError("no fixed-grid oracle route satisfies the operational constraints")
    return best[1]


def row_label_source(row: dict[str, Any]) -> str:
    return str(row.get("label_source", ""))


def diagnose(
    features_path: Path,
    dataset_path: Path,
    stage_b_report_path: Path,
    stage_b_policy_path: Path,
    v3_model_path: Path,
    v3_manifest_path: Path,
    v3_calibrator_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    from catboost import CatBoostClassifier

    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite Stage C0 diagnosis: {output_path}")
    stage_b = json.loads(stage_b_report_path.read_text())
    if stage_b.get("status") != "LOCKED_NON_PROMOTABLE":
        raise ValueError("Stage C0 requires a locked non-promotable Stage B report")
    if stage_b.get("bindings", {}).get("features_sha256") != _sha256(features_path):
        raise ValueError("Stage B report does not bind the supplied features")
    features = [row for row in _jsonl(features_path) if row.get("split") == "candidate_selection"]
    reviewed = [row for row in features if row_label_source(row) == "llm_assisted_v4"]
    if len(features) != int(stage_b["candidate_rows"]) or len(reviewed) != int(stage_b["stage_b"]["reviewed_semantic_rows"]):
        raise ValueError("Stage C0 candidate composition does not match Stage B")

    examples: dict[str, AceDatasetExample] = {}
    with dataset_path.open() as source:
        for line in source:
            if line.strip():
                value = AceDatasetExample.model_validate_json(line)
                examples[value.identity.example_id] = value
    if any(row["example_id"] not in examples for row in reviewed):
        raise ValueError("Stage C0 dataset is missing reviewed feature rows")

    manifest = json.loads(v3_manifest_path.read_text())
    if manifest.get("artifact_sha256") != _sha256(v3_model_path):
        raise ValueError("locked v3 model hash mismatch")
    model = CatBoostClassifier()
    model.load_model(v3_model_path)
    raw = model.predict_proba([feature_vector(row, manifest["feature_names"]) for row in features])[:, 1]
    probabilities = _calibrated(load(v3_calibrator_path), raw)
    policy = json.loads(stage_b_policy_path.read_text())
    predicted = [
        predict_policy_treatment(
            row,
            probability,
            float(policy["threshold"]),
            semantic_contradiction_threshold=policy.get("semantic_contradiction_threshold"),
            semantic_neutral_threshold=policy.get("semantic_neutral_threshold"),
        )
        for row, probability in zip(features, probabilities, strict=True)
    ]

    feature_index = {row["example_id"]: index for index, row in enumerate(features)}
    confusion: Counter[str] = Counter()
    false_negatives: Counter[str] = Counter()
    actual_metrics: dict[str, dict[str, int | float]] = {}
    for row in reviewed:
        example = examples[row["example_id"]]
        actual = example.labels.semantic[0].label.value
        semantic_scores = {
            "CONTRADICTION": float(row["semantic_contradiction"]),
            "NEUTRAL": float(row["semantic_neutral"]),
            "ENTAILMENT": float(row["semantic_entailment"]),
        }
        semantic_prediction = max(semantic_scores, key=semantic_scores.__getitem__)
        confusion[f"{actual}->{semantic_prediction}"] += 1
        index = feature_index[row["example_id"]]
        if row["expected_treatment"] != "APPROVE" and predicted[index] == "APPROVE":
            false_negatives[f"{actual}->{semantic_prediction}"] += 1
    for label in ("CONTRADICTION", "NEUTRAL", "ENTAILMENT"):
        values = [row for row in reviewed if examples[row["example_id"]].labels.semantic[0].label.value == label]
        correct = sum(
            max(
                ("CONTRADICTION", "NEUTRAL", "ENTAILMENT"),
                key=lambda name: float(row[f"semantic_{name.lower()}"]),
            )
            == label
            for row in values
        )
        actual_metrics[label] = {
            "rows": len(values),
            "nli_recall": correct / len(values) if values else 0.0,
        }

    oracle = oracle_routing(features, probabilities)
    reviewed_violations = int(stage_b["stage_b"]["reviewed_semantic_violation_rows"])
    checks = {
        "stage_b_below_target": float(stage_b["stage_b"]["reviewed_semantic_recall"]) < SEMANTIC_TARGET,
        "minimum_reviewed_violations": reviewed_violations >= REVIEWED_VIOLATIONS_MIN,
        "oracle_semantic_headroom": float(oracle["semantic_recall"]) >= ORACLE_SEMANTIC_RECALL_PROCEED,
        "oracle_operational_recall": float(oracle["operational_recall"]) >= OPERATIONAL_RECALL_MIN,
        "oracle_false_step_up": float(oracle["false_step_up_rate"]) <= FALSE_STEP_UP_MAX,
    }
    report = {
        "diagnosis_version": "stage-c0-v1",
        "status": "PROCEED_STAGE_C1" if all(checks.values()) else "STOP_STAGE_C0",
        "bindings": {
            "features_sha256": _sha256(features_path),
            "dataset_sha256": _sha256(dataset_path),
            "stage_b_report_sha256": _sha256(stage_b_report_path),
            "stage_b_policy_sha256": _sha256(stage_b_policy_path),
        },
        "stage_b_semantic_recall": stage_b["stage_b"]["reviewed_semantic_recall"],
        "semantic_target": SEMANTIC_TARGET,
        "reviewed_rows": len(reviewed),
        "reviewed_violation_rows": reviewed_violations,
        "semantic_confusion": dict(sorted(confusion.items())),
        "false_negatives": dict(sorted(false_negatives.items())),
        "semantic_label_metrics": actual_metrics,
        "fixed_grid_oracle_diagnostic": oracle,
        "proceed_thresholds": {
            "oracle_semantic_recall_min": ORACLE_SEMANTIC_RECALL_PROCEED,
            "operational_recall_min": OPERATIONAL_RECALL_MIN,
            "false_step_up_max": FALSE_STEP_UP_MAX,
            "reviewed_violations_min": REVIEWED_VIOLATIONS_MIN,
        },
        "checks": checks,
        "candidate_reuse": {
            "diagnostic_use_only": True,
            "training_authorized": False,
            "policy_tuning_authorized": False,
            "future_evaluation_authorized": False,
        },
        "llm_spend_authorized": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose Stage B semantic failures and gate Stage C1")
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--stage-b-report", type=Path, required=True)
    parser.add_argument("--stage-b-policy", type=Path, required=True)
    parser.add_argument("--v3-model", type=Path, required=True)
    parser.add_argument("--v3-manifest", type=Path, required=True)
    parser.add_argument("--v3-calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(
        args.features,
        args.dataset,
        args.stage_b_report,
        args.stage_b_policy,
        args.v3_model,
        args.v3_manifest,
        args.v3_calibrator,
        args.output,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
