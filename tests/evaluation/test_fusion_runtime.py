from __future__ import annotations

import hashlib
import json

import pytest
from app.structured import FusionArtifactScorer

from ml.data.generate_dataset import write_dataset
from ml.evaluation.evaluate import evaluate
from ml.features.schema import FEATURE_NAMES, FEATURE_VERSION
from ml.fusion.promote import promote
from ml.fusion.train_fusion import train


def test_trained_fusion_bundle_loads_in_live_runtime(tmp_path) -> None:
    data_dir = tmp_path / "data"
    artifact_dir = tmp_path / "artifacts"
    write_dataset(data_dir)
    dataset_path = data_dir / "mandate-cart-pairs.jsonl"
    rows = [json.loads(line) for line in dataset_path.read_text().splitlines()]
    dataset_path.write_text(
        "".join(
            json.dumps(
                {
                    **row,
                    "example_id": f"runtime-test-{index}",
                    "dataset_version": "ace-canonical-features-v2",
                }
            )
            + "\n"
            for index, row in enumerate(rows)
        )
    )
    dataset_path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "feature_version": FEATURE_VERSION,
                "feature_names": FEATURE_NAMES,
                "features_sha256": hashlib.sha256(
                    dataset_path.read_bytes()
                ).hexdigest(),
                "semantic_model_versions": ["heuristic-nli-v1"],
                "semantic_predictions_sha256": "a" * 64,
            }
        )
    )
    manifest = train(
        dataset_path,
        artifact_dir,
        feature_profile="shortcut-safe-v2",
        target_mode="policy_intervention",
    )
    manifest_path = artifact_dir / "fusion-v2.manifest.json"
    with pytest.raises(RuntimeError, match="promotion gate"):
        FusionArtifactScorer(artifact_dir, manifest_path)

    report_path = tmp_path / "evaluation.json"
    report = evaluate(dataset_path, artifact_dir, report_path)
    assert report["schema_version"] == "golden-evaluation-v2"
    assert report["evaluation_split"] == "golden"
    assert set(report["experiments"]) >= {
        "rules_only",
        "semantic_only",
        "catboost_only",
        "rules_semantic_catboost",
        "full_calibrated_ensemble",
    }

    locked_dataset = data_dir / "locked-features.jsonl"
    trained_rows = [json.loads(line) for line in dataset_path.read_text().splitlines()]
    locked_rows = [
        {
            **row,
            "example_id": f"locked-{row['example_id']}",
            "seed_id": f"locked-{row['seed_id']}",
        }
        for row in trained_rows
        if row["split"] == "golden"
    ]
    locked_dataset.write_text(
        "".join(json.dumps(row) + "\n" for row in locked_rows)
    )
    locked_dataset.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "feature_version": FEATURE_VERSION,
                "feature_names": FEATURE_NAMES,
                "features_sha256": hashlib.sha256(
                    locked_dataset.read_bytes()
                ).hexdigest(),
                "semantic_model_versions": manifest["semantic_model_versions"],
                "semantic_predictions_sha256": "c" * 64,
                "semantic_predictions_manifest_sha256": "d" * 64,
                "semantic_model_tree_sha256": "e" * 64,
                "semantic_training_manifest_sha256": "f" * 64,
            }
        )
    )
    selection_report = tmp_path / "selection.json"
    selection_report.write_text(
        json.dumps(
            {
                "status": "selected",
                "golden_rows_scored": 0,
                "replacement_holdout_rows_scored": 0,
                "selected_candidate": {
                    "artifact_dir": str(artifact_dir),
                    "artifact_manifest_sha256": hashlib.sha256(
                        (artifact_dir / "fusion-v2.manifest.json").read_bytes()
                    ).hexdigest(),
                },
            }
        )
    )
    locked_report = evaluate(
        locked_dataset,
        artifact_dir,
        tmp_path / "locked-evaluation.json",
        training_dataset_path=dataset_path,
        selection_report_path=selection_report,
    )
    assert locked_report["evaluation_protocol"] == "locked-replacement-holdout-v1"
    assert locked_report["evaluation_dataset_sha256"] == hashlib.sha256(
        locked_dataset.read_bytes()
    ).hexdigest()
    assert locked_report["dataset_sha256"] == manifest["dataset_sha256"]
    assert locked_report["integrity_checks"]["candidate_selection_checksum_bound"]

    # This deliberately tiny runtime fixture is not a production calibration set. Turn
    # its checksum-bound report into a passing gate attestation only to exercise loading
    # of the promoted artifact; gate behavior itself is covered independently below.
    report["status"] = "passed"
    report["gate"]["status"] = "passed"
    for criterion in report["gate"]["criteria"].values():
        criterion["passed"] = True
    report_path.write_text(json.dumps(report))
    serving_manifest = artifact_dir / "fusion-v2.serving.manifest.json"
    promote(manifest_path, report_path, serving_manifest)
    scorer = FusionArtifactScorer(artifact_dir, serving_manifest)
    assert manifest["serving_approved"] is False
    assert scorer.catboost_version == "fusion-catboost-v2"
    assert scorer.stacker_version == "logistic-stacker-v2"
    assert scorer.calibrator_version == "platt-calibrator-v2"
    assert scorer.step_up_threshold is not None

    tampered_manifest = json.loads(serving_manifest.read_text())
    tampered_manifest["stack_features"] = list(
        reversed(tampered_manifest["stack_features"])
    )
    tampered_path = artifact_dir / "tampered-stack.manifest.json"
    tampered_path.write_text(json.dumps(tampered_manifest))
    with pytest.raises(RuntimeError, match="stack feature profile"):
        FusionArtifactScorer(artifact_dir, tampered_path)


def test_promotion_rejects_failed_evaluation(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.json"
    output = tmp_path / "serving.json"
    manifest.write_text(
        '{"model_version":"fusion-v2","dataset_sha256":"abc","model_hold_enabled":false}'
    )
    report.write_text('{"status":"failed_gate"}')
    with pytest.raises(ValueError, match="passed"):
        promote(manifest, report, output)


def test_promotion_rejects_inconsistent_gate_attestation(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.json"
    output = tmp_path / "serving.json"
    manifest.write_text(
        '{"model_version":"fusion-v2","dataset_sha256":"abc","model_hold_enabled":false}'
    )
    report.write_text(
        json.dumps(
            {
                "schema_version": "golden-evaluation-v2",
                "evaluation_split": "golden",
                "status": "passed",
                "gate": {
                    "status": "passed",
                    "criteria": {"recall": {"passed": False}},
                },
            }
        )
    )
    with pytest.raises(ValueError, match="failed promotion criterion"):
        promote(manifest, report, output)


def test_policy_target_trains_with_shortcut_safe_profile(tmp_path) -> None:
    data_dir = tmp_path / "data"
    artifact_dir = tmp_path / "artifacts"
    write_dataset(data_dir)
    dataset_path = data_dir / "mandate-cart-pairs.jsonl"
    rows = [json.loads(line) for line in dataset_path.read_text().splitlines()]
    dataset_path.write_text(
        "".join(
            json.dumps(
                {
                    **row,
                    "example_id": f"remediation-test-{index}",
                    "dataset_version": "ace-canonical-features-v2",
                }
            )
            + "\n"
            for index, row in enumerate(rows)
        )
    )
    dataset_path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "feature_version": FEATURE_VERSION,
                "feature_names": FEATURE_NAMES,
                "features_sha256": hashlib.sha256(
                    dataset_path.read_bytes()
                ).hexdigest(),
                "semantic_model_versions": ["heuristic-nli-v1"],
                "semantic_predictions_sha256": "b" * 64,
            }
        )
    )

    manifest = train(
        dataset_path,
        artifact_dir,
        feature_profile="shortcut-safe-v2",
        target_mode="policy_intervention",
    )

    assert manifest["feature_profile"] == "shortcut-safe-v2"
    assert manifest["target_mode"] == "policy_intervention"
    assert "line_item_count" not in manifest["feature_names"]
    assert manifest["threshold_selection_method"] == "complete-policy-validation-v1"
    assert manifest["threshold_selection_rows"] > manifest["validation_label_counts"]["0"]


def test_promotion_rejects_full_profile_even_with_passing_report(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    report_path = tmp_path / "report.json"
    manifest = {
        "model_version": "fusion-v2",
        "dataset_sha256": "abc",
        "model_hold_enabled": False,
        "feature_profile": "full-v2",
        "feature_names": FEATURE_NAMES,
        "target_mode": "policy_intervention",
        "threshold_selection_method": "complete-policy-validation-v1",
    }
    manifest_path.write_text(json.dumps(manifest))
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "golden-evaluation-v2",
                "evaluation_split": "golden",
                "status": "passed",
                "model_version": "fusion-v2",
                "dataset_sha256": "abc",
                "artifact_manifest_sha256": hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest(),
                "gate": {
                    "status": "passed",
                    "criteria": {"recall": {"passed": True}},
                },
            }
        )
    )
    with pytest.raises(ValueError, match="line-item shortcut"):
        promote(manifest_path, report_path, tmp_path / "serving.json")
