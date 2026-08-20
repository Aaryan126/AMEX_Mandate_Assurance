from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.evaluation.metrics import (
    by_attack_family,
    by_cohort,
    expected_calibration_error,
    treatment_metrics,
)
from ml.features.schema import (
    feature_profile_for_names,
    feature_vector,
    stack_feature_names_for_profile,
)
from ml.fusion.train_fusion import _stack_row, logistic_probability
from ml.tabular.train_catboost import load_rows, validate_feature_dataset

FALSE_STEP_UP_TARGET = 0.10


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_artifacts(
    dataset_path: Path,
    artifact_dir: Path,
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    feature_manifest = validate_feature_dataset(dataset_path, rows)
    manifest_path = artifact_dir / "fusion-v2.manifest.json"
    if not manifest_path.is_file():
        raise ValueError("fusion evaluation requires an artifact manifest")
    manifest = json.loads(manifest_path.read_text())
    required_files = {
        "base_artifact": "base_sha256",
        "fusion_artifact": "fusion_sha256",
    }
    for artifact_key, digest_key in required_files.items():
        name = manifest.get(artifact_key)
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError(f"invalid {artifact_key} in fusion manifest")
        path = artifact_dir / name
        if not path.is_file() or _sha256(path) != manifest.get(digest_key):
            raise ValueError(f"{artifact_key} checksum does not match fusion manifest")
    if manifest.get("dataset_sha256") != _sha256(dataset_path):
        raise ValueError("fusion artifact is not bound to this feature dataset")
    if manifest.get("feature_manifest_sha256") != feature_manifest["manifest_sha256"]:
        raise ValueError("fusion artifact is not bound to this feature manifest")
    model_feature_names = [str(value) for value in manifest.get("feature_names", [])]
    feature_profile = feature_profile_for_names(model_feature_names)
    if manifest.get("feature_profile", feature_profile) != feature_profile:
        raise ValueError("fusion artifact feature profile is inconsistent")
    if manifest.get("stack_features") != stack_feature_names_for_profile(feature_profile):
        raise ValueError("fusion artifact stack feature profile is inconsistent")
    if manifest.get("canonical_feature_names", feature_manifest.get("feature_names")) != (
        feature_manifest.get("feature_names")
    ):
        raise ValueError("fusion artifact canonical feature contract does not match the dataset")
    if manifest.get("semantic_predictions_sha256") != feature_manifest.get(
        "semantic_predictions_sha256"
    ):
        raise ValueError("fusion and feature semantic bindings do not match")
    if manifest.get("serving_approved") is not False:
        raise ValueError("golden evaluation accepts only an unpromoted experiment manifest")
    if manifest.get("model_hold_enabled") is not False:
        raise ValueError("model-only HOLD must remain disabled")
    return manifest, feature_manifest


def _validate_locked_selection(
    selection_report_path: Path, artifact_dir: Path
) -> dict[str, Any]:
    report = json.loads(selection_report_path.read_text())
    if report.get("status") != "selected":
        raise ValueError("locked evaluation requires a completed candidate selection")
    selected = report.get("selected_candidate")
    if not isinstance(selected, dict):
        raise TypeError("candidate selection does not identify an artifact")
    selected_dir = Path(str(selected.get("artifact_dir", "")))
    if selected_dir.resolve() != artifact_dir.resolve():
        raise ValueError("evaluation artifact does not match the selected candidate")
    manifest_path = artifact_dir / "fusion-v2.manifest.json"
    if selected.get("artifact_manifest_sha256") != _sha256(manifest_path):
        raise ValueError("selected candidate manifest checksum has changed")
    if report.get("golden_rows_scored") != 0:
        raise ValueError("candidate selection accessed the previous golden split")
    if report.get("replacement_holdout_rows_scored") != 0:
        raise ValueError("candidate selection accessed the replacement holdout")
    return report


def _validate_external_feature_contract(
    dataset_path: Path,
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    feature_manifest = validate_feature_dataset(dataset_path, rows)
    if feature_manifest.get("feature_names") != manifest.get("canonical_feature_names"):
        raise ValueError("evaluation feature contract does not match the selected model")
    if feature_manifest.get("semantic_model_versions") != manifest.get(
        "semantic_model_versions"
    ):
        raise ValueError("evaluation semantic model version does not match training")
    for field in (
        "semantic_predictions_manifest_sha256",
        "semantic_model_tree_sha256",
        "semantic_training_manifest_sha256",
    ):
        value = feature_manifest.get(field)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"locked evaluation feature manifest is missing {field}")
    return feature_manifest


def _fixed_false_positive_point(
    labels: list[int], probabilities: list[float], target: float
) -> dict[str, float | int]:
    negatives = sum(label == 0 for label in labels)
    positives = sum(label == 1 for label in labels)
    if not negatives or not positives:
        raise ValueError("fixed-FPR evaluation requires both binary classes")
    candidates = [math.inf, *sorted(set(probabilities), reverse=True)]
    best: tuple[float, float, int, int] | None = None
    for threshold in candidates:
        false_positives = sum(
            label == 0 and probability >= threshold
            for label, probability in zip(labels, probabilities, strict=True)
        )
        if false_positives / negatives > target + 1e-12:
            continue
        true_positives = sum(
            label == 1 and probability >= threshold
            for label, probability in zip(labels, probabilities, strict=True)
        )
        candidate = (true_positives / positives, threshold, true_positives, false_positives)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        raise AssertionError("infinite threshold must satisfy the false-positive target")
    recall, threshold, true_positives, false_positives = best
    predicted_positives = true_positives + false_positives
    return {
        "target_false_positive_rate": target,
        "evaluation_only_threshold": threshold,
        "violation_recall": recall,
        "false_positive_rate": false_positives / negatives,
        "precision": true_positives / predicted_positives if predicted_positives else 0.0,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "positive_rows": positives,
        "negative_rows": negatives,
    }


def _ranking_metrics(labels: list[int], probabilities: list[float]) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    return {
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "expected_calibration_error": expected_calibration_error(labels, probabilities),
        "recall_at_fixed_false_positive_rate": _fixed_false_positive_point(
            labels, probabilities, FALSE_STEP_UP_TARGET
        ),
        "probability_range": [min(probabilities), max(probabilities)],
    }


def _policy_metrics(expected: list[str], predicted: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = treatment_metrics(expected, predicted)
    violation_rows = sum(value != "APPROVE" for value in expected)
    interventions = sum(value != "APPROVE" for value in predicted)
    correct_interventions = sum(
        actual != "APPROVE" and result != "APPROVE"
        for actual, result in zip(expected, predicted, strict=True)
    )
    metrics.update(
        {
            "treatment_accuracy": sum(
                actual == result
                for actual, result in zip(expected, predicted, strict=True)
            )
            / len(expected),
            "intervention_precision": (
                correct_interventions / interventions if interventions else 0.0
            ),
            "intervention_rate": interventions / len(expected),
            "expected_treatment_counts": dict(sorted(Counter(expected).items())),
            "predicted_treatment_counts": dict(sorted(Counter(predicted).items())),
            "violation_rows": violation_rows,
        }
    )
    return metrics


def _experiment(
    name: str,
    probabilities: list[float],
    labels: list[int],
    labeled_positions: list[int],
    treatments: list[str],
    expected: list[str],
    operating_threshold: float | str,
) -> dict[str, Any]:
    labeled_probabilities = [probabilities[index] for index in labeled_positions]
    return {
        "name": name,
        "operating_threshold": operating_threshold,
        "ranking": _ranking_metrics(labels, labeled_probabilities),
        "policy": _policy_metrics(expected, treatments),
    }


def _latency_summary(samples_ms: list[float], batch_ms: float) -> dict[str, float | int]:
    import numpy as np

    return {
        "rows": len(samples_ms),
        "single_row_p50_ms": float(np.percentile(samples_ms, 50)),
        "single_row_p95_ms": float(np.percentile(samples_ms, 95)),
        "single_row_max_ms": max(samples_ms),
        "batch_total_ms": batch_ms,
        "batch_average_per_row_ms": batch_ms / len(samples_ms),
    }


def _score_fusion(
    rows: list[dict[str, Any]],
    base_model: Any,
    bundle: dict[str, Any],
    feature_names: list[str],
    stack_features: list[str],
) -> tuple[list[float], list[float], list[float]]:
    base = [
        float(value)
        for value in base_model.predict_proba(
            [feature_vector(row, feature_names) for row in rows]
        )[:, 1]
    ]
    stack = [
        logistic_probability(
            bundle["stacker"], _stack_row(row, probability, stack_features)
        )
        for row, probability in zip(rows, base, strict=True)
    ]
    calibrated = [
        logistic_probability(bundle["calibrator"], [probability])
        for probability in stack
    ]
    return base, stack, calibrated


def _treatments(
    rows: list[dict[str, Any]],
    probabilities: list[float],
    threshold: float,
    include_rules: bool,
    include_semantic: bool,
) -> list[str]:
    predictions: list[str] = []
    for row, probability in zip(rows, probabilities, strict=True):
        if include_rules and row.get("critical_hold_count", 0):
            predictions.append("HOLD")
        elif (
            (include_rules and row["hard_fail_count"])
            or (
                include_semantic
                and (
                    row["semantic_contradiction"] >= 0.8
                    or row["semantic_neutral"] >= 0.6
                )
            )
            or probability >= threshold
        ):
            predictions.append("STEP_UP")
        else:
            predictions.append("APPROVE")
    return predictions


def _criterion(actual: float, operator: str, limit: float) -> dict[str, Any]:
    passed = actual >= limit if operator == ">=" else actual <= limit
    return {"actual": actual, "operator": operator, "limit": limit, "passed": passed}


def evaluate(
    dataset_path: Path,
    artifact_dir: Path,
    output_path: Path,
    *,
    training_dataset_path: Path | None = None,
    selection_report_path: Path | None = None,
) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise RuntimeError(
            "Install services/api[ml] before running evaluation"
        ) from exc

    if (training_dataset_path is None) != (selection_report_path is None):
        raise ValueError(
            "locked evaluation requires both training dataset and selection report"
        )
    rows = load_rows(dataset_path)
    locked_evaluation = training_dataset_path is not None
    selection_report: dict[str, Any] | None = None
    if training_dataset_path is None:
        manifest, feature_manifest = _validate_artifacts(
            dataset_path, artifact_dir, rows
        )
        training_feature_manifest = feature_manifest
    else:
        training_rows = load_rows(training_dataset_path)
        manifest, training_feature_manifest = _validate_artifacts(
            training_dataset_path, artifact_dir, training_rows
        )
        feature_manifest = _validate_external_feature_contract(
            dataset_path, rows, manifest
        )
        assert selection_report_path is not None
        selection_report = _validate_locked_selection(
            selection_report_path, artifact_dir
        )
    golden = [row for row in rows if row["split"] == "golden"]
    if not golden:
        raise ValueError("evaluation requires a non-empty golden split")
    labeled_positions = [
        index for index, row in enumerate(golden) if row["label"] is not None
    ]
    treatment_positions = [
        index for index, row in enumerate(golden) if row["expected_treatment"] is not None
    ]
    if not labeled_positions or len(treatment_positions) != len(golden):
        raise ValueError("golden split requires binary labels and complete treatment labels")
    labels = [int(golden[index]["label"]) for index in labeled_positions]
    if set(labels) != {0, 1}:
        raise ValueError("golden binary labels must contain both classes")
    expected = [str(row["expected_treatment"]) for row in golden]

    base_model = CatBoostClassifier()
    base_model.load_model(artifact_dir / manifest["base_artifact"])
    bundle = json.loads((artifact_dir / manifest["fusion_artifact"]).read_text())
    model_feature_names = [str(value) for value in manifest["feature_names"]]
    stack_features = [str(value) for value in manifest["stack_features"]]
    batch_start = time.perf_counter()
    base, stack, calibrated = _score_fusion(
        golden, base_model, bundle, model_feature_names, stack_features
    )
    batch_ms = (time.perf_counter() - batch_start) * 1000

    zero = [0.0] * len(golden)
    rule_scores = [
        1.0 if row["critical_hold_count"] else 0.75 if row["hard_fail_count"] else 0.0
        for row in golden
    ]
    semantic_scores = [
        max(float(row["semantic_contradiction"]), float(row["semantic_neutral"]))
        for row in golden
    ]
    rule_treatments = _treatments(golden, zero, 1.1, True, False)
    semantic_treatments = _treatments(golden, zero, 1.1, False, True)
    catboost_treatments = _treatments(golden, base, 0.5, False, False)
    core_treatments = _treatments(golden, stack, 0.5, True, True)
    final_threshold = float(manifest["model_step_up_threshold"])
    final_treatments = _treatments(golden, calibrated, final_threshold, True, True)

    experiments = {
        "rules_only": _experiment(
            "deterministic rules only",
            rule_scores,
            labels,
            labeled_positions,
            rule_treatments,
            expected,
            "declared rule severities",
        ),
        "semantic_only": _experiment(
            "semantic model only",
            semantic_scores,
            labels,
            labeled_positions,
            semantic_treatments,
            expected,
            "contradiction>=0.8 or neutral>=0.6",
        ),
        "catboost_only": _experiment(
            "CatBoost with semantic features",
            base,
            labels,
            labeled_positions,
            catboost_treatments,
            expected,
            0.5,
        ),
        "rules_semantic_catboost": _experiment(
            "rules + semantic + CatBoost stacker",
            stack,
            labels,
            labeled_positions,
            core_treatments,
            expected,
            0.5,
        ),
        "full_calibrated_ensemble": _experiment(
            "full calibrated ensemble and deterministic policy",
            calibrated,
            labels,
            labeled_positions,
            final_treatments,
            expected,
            final_threshold,
        ),
        "catboost_without_semantic": {
            "status": "not_run",
            "reason": "requires a separately approved retraining run; zeroing features at inference would not be a valid ablation",
        },
        "tabm_challenger": {
            "status": "not_run",
            "reason": "no trained TabM artifact exists in the approved fast-track workflow",
        },
    }

    single_row_samples: list[float] = []
    for row in golden:
        started = time.perf_counter()
        row_base, row_stack, row_calibrated = _score_fusion(
            [row], base_model, bundle, model_feature_names, stack_features
        )
        predict_treatment(row, row_calibrated[0], final_threshold)
        if not row_base or not row_stack:
            raise AssertionError("single-row scorer returned an empty prediction")
        single_row_samples.append((time.perf_counter() - started) * 1000)

    normalized_rows = [{**row, "line_item_count": 1} for row in golden]
    _, _, normalized_calibrated = _score_fusion(
        normalized_rows,
        base_model,
        bundle,
        model_feature_names,
        stack_features,
    )
    normalized_treatments = _treatments(
        normalized_rows, normalized_calibrated, final_threshold, True, True
    )
    deltas = [
        abs(original - normalized)
        for original, normalized in zip(calibrated, normalized_calibrated, strict=True)
    ]
    import numpy as np

    shortcut_audit = {
        "method": "evaluation-only perturbation setting line_item_count to 1; this is a sensitivity test, not a causal estimate",
        "mean_absolute_probability_delta": float(np.mean(deltas)),
        "p95_absolute_probability_delta": float(np.percentile(deltas, 95)),
        "max_absolute_probability_delta": max(deltas),
        "treatment_flip_rate": sum(
            original != normalized
            for original, normalized in zip(
                final_treatments, normalized_treatments, strict=True
            )
        )
        / len(golden),
        "observed_line_item_count_distribution": {
            str(key): value
            for key, value in sorted(Counter(row["line_item_count"] for row in golden).items())
        },
    }

    final = experiments["full_calibrated_ensemble"]
    catboost = experiments["catboost_only"]
    assert "ranking" in final and "policy" in final and "ranking" in catboost
    attack_families = by_attack_family(golden, final_treatments)
    eligible_attack_recalls = [
        float(value["violation_recall"])
        for value in attack_families.values()
        if int(value["violation_rows"]) >= 25
    ]
    minimum_attack_recall = min(eligible_attack_recalls, default=1.0)
    pr_auc_delta = float(final["ranking"]["pr_auc"]) - float(
        catboost["ranking"]["pr_auc"]
    )
    fixed_recall_delta = float(
        final["ranking"]["recall_at_fixed_false_positive_rate"]["violation_recall"]
    ) - float(
        catboost["ranking"]["recall_at_fixed_false_positive_rate"]["violation_recall"]
    )
    criteria = {
        "operational_violation_recall": _criterion(
            float(final["policy"]["violation_recall"]), ">=", 0.90
        ),
        "operational_false_step_up_rate": _criterion(
            float(final["policy"]["false_step_up_rate"]), "<=", 0.10
        ),
        "operational_false_decline_rate": _criterion(
            float(final["policy"]["false_decline_rate"]), "<=", 0.02
        ),
        "pr_auc": _criterion(float(final["ranking"]["pr_auc"]), ">=", 0.80),
        "expected_calibration_error": _criterion(
            float(final["ranking"]["expected_calibration_error"]), "<=", 0.08
        ),
        "minimum_supported_attack_family_recall": _criterion(
            minimum_attack_recall, ">=", 0.80
        ),
        "pr_auc_delta_vs_catboost": _criterion(pr_auc_delta, ">=", -0.005),
        "fixed_fpr_recall_delta_vs_catboost": _criterion(
            fixed_recall_delta, ">=", -0.02
        ),
    }
    status = "passed" if all(value["passed"] for value in criteria.values()) else "failed_gate"
    report = {
        "schema_version": "golden-evaluation-v2",
        "dataset_version": manifest["dataset_version"],
        "model_version": manifest["model_version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "feature_manifest_sha256": manifest["feature_manifest_sha256"],
        "semantic_predictions_sha256": manifest["semantic_predictions_sha256"],
        "evaluation_protocol": (
            "locked-replacement-holdout-v1" if locked_evaluation else "bound-golden-v2"
        ),
        "evaluation_dataset_sha256": _sha256(dataset_path),
        "evaluation_feature_manifest_sha256": feature_manifest["manifest_sha256"],
        "evaluation_semantic_predictions_sha256": feature_manifest[
            "semantic_predictions_sha256"
        ],
        "evaluation_semantic_predictions_manifest_sha256": feature_manifest.get(
            "semantic_predictions_manifest_sha256"
        ),
        "evaluation_semantic_model_tree_sha256": feature_manifest.get(
            "semantic_model_tree_sha256"
        ),
        "selection_report_sha256": (
            _sha256(selection_report_path)
            if selection_report_path is not None
            else None
        ),
        "artifact_manifest_sha256": _sha256(artifact_dir / "fusion-v2.manifest.json"),
        "status": status,
        "evaluation_split": "golden",
        "golden_rows": {
            "total": len(golden),
            "binary_labeled": len(labeled_positions),
            "treatment_labeled": len(treatment_positions),
            "binary_label_counts": dict(sorted(Counter(labels).items())),
        },
        "integrity_checks": {
            "feature_dataset_checksum_bound": True,
            "feature_manifest_checksum_bound": True,
            "artifact_training_dataset_checksum_bound": True,
            "evaluation_dataset_separately_checksum_bound": True,
            "model_artifacts_checksum_bound": True,
            "semantic_predictions_checksum_bound": True,
            "group_splits_disjoint": True,
            "experiment_manifest_unpromoted": True,
            "model_only_hold_disabled": True,
            "feature_manifest_rows": feature_manifest["rows"],
            "training_feature_manifest_rows": training_feature_manifest["rows"],
            "feature_profile": feature_profile_for_names(model_feature_names),
            "candidate_selection_checksum_bound": selection_report is not None,
        },
        "gate": {
            "status": status,
            "criteria": criteria,
            "note": "A passed evaluation is necessary but not sufficient for serving promotion; promotion is a separate explicit action.",
        },
        "primary_result": {
            "metric": "violation recall at false-positive rate <= 0.10",
            **final["ranking"]["recall_at_fixed_false_positive_rate"],
        },
        "metrics": {
            **final["policy"],
            "binary_violation_recall": final["ranking"][
                "recall_at_fixed_false_positive_rate"
            ]["violation_recall"],
            "high_risk_precision": final["ranking"][
                "recall_at_fixed_false_positive_rate"
            ]["precision"],
            "pr_auc": final["ranking"]["pr_auc"],
            "expected_calibration_error": final["ranking"][
                "expected_calibration_error"
            ],
        },
        "experiments": experiments,
        "comparison": {
            "full_minus_catboost_pr_auc": pr_auc_delta,
            "full_minus_catboost_fixed_fpr_recall": fixed_recall_delta,
        },
        "attack_families": attack_families,
        "cohorts": {
            "dataset": by_cohort(
                golden, final_treatments, lambda row: str(row.get("dataset", "unknown"))
            ),
            "domain": by_cohort(
                golden, final_treatments, lambda row: str(row.get("domain", "unknown"))
            ),
            "merchant_category": by_cohort(
                golden, final_treatments, lambda row: str(row["merchant_category"])
            ),
            "evidence_sufficiency": by_cohort(
                golden, final_treatments, lambda row: str(row["evidence_sufficiency"])
            ),
            "label_source": by_cohort(
                golden,
                final_treatments,
                lambda row: str(row.get("label_source", "unknown")),
            ),
            "line_item_count": by_cohort(
                golden, final_treatments, lambda row: str(row["line_item_count"])
            ),
        },
        "shortcut_audit": shortcut_audit,
        "latency_ms": _latency_summary(single_row_samples, batch_ms),
        "limitations": [
            "LLM-reviewed labels remain provisional pending stratified human audit.",
            "CatBoost-without-semantic and TabM require separately approved training and were not fabricated through inference-time feature zeroing.",
            "The fixed-FPR threshold in the primary result is evaluation-only; the operational policy uses the validation-derived manifest threshold.",
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
        default=Path("ml/data/generated/features-v2.jsonl"),
    )
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/models"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/evaluation-summary.json"),
    )
    parser.add_argument("--training-dataset", type=Path)
    parser.add_argument("--selection-report", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            evaluate(
                args.dataset,
                args.artifacts,
                args.output,
                training_dataset_path=args.training_dataset,
                selection_report_path=args.selection_report,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
