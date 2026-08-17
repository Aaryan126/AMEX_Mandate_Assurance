from __future__ import annotations

import json

import pytest
from app.structured import FusionArtifactScorer

from ml.data.generate_dataset import write_dataset
from ml.evaluation.evaluate import evaluate
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
            json.dumps({**row, "dataset_version": "ace-canonical-features-v2"}) + "\n"
            for row in rows
        )
    )
    dataset_path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "semantic_model_versions": ["heuristic-nli-v1"],
                "semantic_predictions_sha256": "test-predictions-sha",
            }
        )
    )
    manifest = train(dataset_path, artifact_dir)
    manifest_path = artifact_dir / "fusion-v2.manifest.json"
    with pytest.raises(RuntimeError, match="promotion gate"):
        FusionArtifactScorer(artifact_dir, manifest_path)

    report_path = tmp_path / "evaluation.json"
    evaluate(dataset_path, artifact_dir, report_path)
    serving_manifest = artifact_dir / "fusion-v2.serving.manifest.json"
    promote(manifest_path, report_path, serving_manifest)
    scorer = FusionArtifactScorer(artifact_dir, serving_manifest)
    assert manifest["serving_approved"] is False
    assert scorer.catboost_version == "fusion-catboost-v2"
    assert scorer.stacker_version == "logistic-stacker-v2"
    assert scorer.calibrator_version == "platt-calibrator-v2"
    assert scorer.step_up_threshold is not None


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
