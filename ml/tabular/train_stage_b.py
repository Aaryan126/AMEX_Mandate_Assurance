from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from app.feature_contract_v3 import FEATURE_NAMES, FEATURE_VERSION, feature_names_for_profile
from joblib import dump, load
from sklearn.linear_model import LogisticRegression

from ml.evaluation.metrics import expected_calibration_error
from ml.features.schema import feature_vector as feature_vector_v2
from ml.fusion.baselines_v3 import _quality
from ml.fusion.policy_selection import policy_metrics, select_policy_configuration
from ml.tabular.train_v4 import _fit, _matrix, _split_training, _target

ROLE_COUNTS = {"train_fit": 4_700, "calibration": 1_200, "policy_tuning": 1_200}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def _calibrated(calibrator: Any, probabilities: Any) -> list[float]:
    logits = [[math.log(value / (1 - value))] for raw in probabilities for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]]
    return [float(value) for value in calibrator.predict_proba(logits)[:, 1]]


def _confidence_weights(rows: list[dict[str, Any]]) -> list[float]:
    weak = {"weak_policy_v3", "weak_policy_v4", "weak_esci_mapping"}
    return [0.5 if row.get("label_source") in weak else 1.0 for row in rows]


def _quality_report(rows: list[dict[str, Any]], probabilities: list[float], policy: dict[str, Any]) -> dict[str, Any]:
    labels = [_target(row) for row in rows]
    quality = _quality(labels, probabilities)
    quality["expected_calibration_error"] = expected_calibration_error(labels, probabilities)
    return {
        "quality": quality,
        "policy": policy_metrics(
            rows,
            probabilities,
            float(policy["threshold"]),
            semantic_contradiction_threshold=policy.get("semantic_contradiction_threshold"),
            semantic_neutral_threshold=policy.get("semantic_neutral_threshold"),
        ),
    }


def _selection_rank(result: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        float(result["policy"]["violation_recall"]),
        -float(result["policy"]["false_step_up_rate"]),
        float(result["quality"]["pr_auc"]),
        -float(result["quality"]["brier"]),
    )


def train(
    features_path: Path,
    output_dir: Path,
    v3_model_path: Path,
    v3_manifest_path: Path,
    v3_calibrator_path: Path,
) -> dict[str, Any]:
    from catboost import CatBoostClassifier

    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite Stage B tabular output: {output_dir}")
    feature_manifest_path = features_path.with_suffix(".manifest.json")
    feature_manifest = json.loads(feature_manifest_path.read_text())
    if feature_manifest.get("features_sha256") != _sha256(features_path):
        raise ValueError("Stage B features checksum mismatch")
    if feature_manifest.get("feature_version") != FEATURE_VERSION or feature_manifest.get("feature_names") != FEATURE_NAMES:
        raise ValueError("Stage B feature contract mismatch")
    rows = _rows(features_path)
    train_rows = [row for row in rows if row["split"] == "train_fit"]
    calibration = [row for row in rows if row["split"] == "calibration"]
    tuning = [row for row in rows if row["split"] == "policy_tuning"]
    if {"train_fit": len(train_rows), "calibration": len(calibration), "policy_tuning": len(tuning)} != ROLE_COUNTS:
        raise ValueError("Stage B development role counts are incompatible")
    internal_train, internal_validation = _split_training(train_rows)
    experiments: list[dict[str, Any]] = []
    best: tuple[float, Any, list[str], str, str] | None = None
    for profile in ("full-v3", "shortcut-safe-v3", "no-semantic-v3"):
        names = feature_names_for_profile(profile)
        for weighting in ("none", "confidence"):
            weights = [1.0] * len(internal_train) if weighting == "none" else _confidence_weights(internal_train)
            model = _fit(internal_train, names, weights, depth=5, l2=6, iterations=300, validation=internal_validation)
            probability = model.predict_proba(_matrix(internal_validation, names))[:, 1]
            quality = _quality([_target(row) for row in internal_validation], probability)
            experiments.append({"feature_profile": profile, "weighting": weighting, "tree_count": int(model.tree_count_), **quality})
            candidate = (float(quality["pr_auc"]), model, names, profile, weighting)
            if best is None or candidate[0] > best[0]:
                best = candidate
    assert best is not None
    _, validation_model, selected_names, selected_profile, selected_weighting = best
    weights = [1.0] * len(train_rows) if selected_weighting == "none" else _confidence_weights(train_rows)
    retrained_model = _fit(train_rows, selected_names, weights, depth=5, l2=6, iterations=max(120, int(validation_model.tree_count_)))
    calibration_raw = retrained_model.predict_proba(_matrix(calibration, selected_names))[:, 1]
    calibration_logits = [[math.log(value / (1 - value))] for raw in calibration_raw for value in [min(max(float(raw), 1e-6), 1 - 1e-6)]]
    retrained_calibrator = LogisticRegression(random_state=2031)
    retrained_calibrator.fit(calibration_logits, [_target(row) for row in calibration])
    retrained_probability = _calibrated(retrained_calibrator, retrained_model.predict_proba(_matrix(tuning, selected_names))[:, 1])
    retrained_policy = select_policy_configuration(tuning, retrained_probability)
    retrained_result = _quality_report(tuning, retrained_probability, retrained_policy)

    v3_manifest = json.loads(v3_manifest_path.read_text())
    if v3_manifest.get("artifact_sha256") != _sha256(v3_model_path):
        raise ValueError("locked v3 model checksum mismatch")
    locked_model = CatBoostClassifier()
    locked_model.load_model(v3_model_path)
    locked_raw = locked_model.predict_proba([feature_vector_v2(row, v3_manifest["feature_names"]) for row in tuning])[:, 1]
    locked_probability = _calibrated(load(v3_calibrator_path), locked_raw)
    locked_policy = select_policy_configuration(tuning, locked_probability)
    locked_result = _quality_report(tuning, locked_probability, locked_policy)

    candidates = {"locked_v3_routed": locked_result, "retrained_v3_semantic_v4": retrained_result}
    selected = max(candidates, key=lambda name: (_selection_rank(candidates[name]), name == "locked_v3_routed"))
    output_dir.mkdir(parents=True, exist_ok=False)
    model_path = output_dir / "catboost-stage-b.cbm"
    retrained_model.save_model(model_path, format="cbm")
    calibrator_path = output_dir / "platt-stage-b.joblib"
    dump(retrained_calibrator, calibrator_path)
    retrained_policy_path = output_dir / "policy-retrained.json"
    retrained_policy_path.write_text(json.dumps(retrained_policy, indent=2, sort_keys=True) + "\n")
    locked_policy_path = output_dir / "policy-locked-v3-routed.json"
    locked_policy_path.write_text(json.dumps(locked_policy, indent=2, sort_keys=True) + "\n")
    manifest = {
        "training_version": "development-v4-semantic-stage-b",
        "features_sha256": _sha256(features_path),
        "features_manifest_sha256": _sha256(feature_manifest_path),
        "semantic_predictions_sha256": feature_manifest["semantic_predictions_sha256"],
        "training_rows": len(train_rows),
        "calibration_rows": len(calibration),
        "policy_tuning_rows": len(tuning),
        "candidate_rows_accessed": 0,
        "selected_candidate": selected,
        "selected_profile": selected_profile,
        "selected_weighting": selected_weighting,
        "retrained_feature_names": selected_names,
        "retrained_model_sha256": _sha256(model_path),
        "retrained_calibrator_sha256": _sha256(calibrator_path),
        "retrained_policy_sha256": _sha256(retrained_policy_path),
        "locked_v3_model_sha256": _sha256(v3_model_path),
        "locked_v3_manifest_sha256": _sha256(v3_manifest_path),
        "locked_v3_calibrator_sha256": _sha256(v3_calibrator_path),
        "locked_v3_policy_sha256": _sha256(locked_policy_path),
        "label_sources": dict(sorted(Counter(row["label_source"] for row in train_rows).items())),
        "production_claim_eligible": False,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    lock = {
        "lock_version": "candidate-pre-evaluation-lock-stage-b",
        "selected_candidate": selected,
        "features_sha256": _sha256(features_path),
        "manifest_sha256": _sha256(manifest_path),
        "candidate_rows_accessed": 0,
        "status": "FROZEN_UNEVALUATED",
    }
    lock_path = output_dir / "candidate-pre-evaluation-lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    report = {
        "selected_candidate": selected,
        "candidate_results_on_policy_tuning": candidates,
        "retrained_experiments": sorted(experiments, key=lambda item: item["pr_auc"], reverse=True),
        "artifacts": manifest,
        "candidate_pre_evaluation_lock_sha256": _sha256(lock_path),
    }
    (output_dir / "training-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and route Stage B structured candidates")
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--v3-model", type=Path, required=True)
    parser.add_argument("--v3-manifest", type=Path, required=True)
    parser.add_argument("--v3-calibrator", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(train(args.features, args.output, args.v3_model, args.v3_manifest, args.v3_calibrator), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
