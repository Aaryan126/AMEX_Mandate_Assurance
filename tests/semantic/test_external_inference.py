from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.semantic.infer_external import infer_external
from ml.semantic.train_multilingual import tree_sha256
from tests.data.test_schema_v2 import example


def test_external_inference_is_bound_label_blind_and_resumable(tmp_path: Path) -> None:
    value = example()
    dataset = tmp_path / "locked.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    model = tmp_path / "model"
    model.mkdir()
    (model / "weights.bin").write_bytes(b"frozen-model")
    semantic_manifest = tmp_path / "semantic-manifest.json"
    semantic_manifest.write_text(
        json.dumps(
            {
                "model_tree_sha256": tree_sha256(model),
                "model_version": "semantic-test-v1",
                "temperature": 2.0,
            }
        )
    )
    output = tmp_path / "predictions.jsonl"

    first = infer_external(
        dataset,
        semantic_manifest,
        model,
        output,
        predictor=lambda rows: [[3.0, 1.0, 0.0] for _ in rows],
    )
    prediction = json.loads(output.read_text())
    assert first["skipped"] is False
    assert first["written"] == 1
    assert prediction["label"] is None
    assert prediction["prediction_origin"] == "locked_external_inference"
    assert sum(
        prediction[name] for name in ("contradiction", "neutral", "entailment")
    ) == pytest.approx(1.0)

    resumed = infer_external(
        dataset,
        semantic_manifest,
        model,
        output,
        predictor=lambda _: pytest.fail("bound output must resume without inference"),
    )
    assert resumed["skipped"] is True


def test_external_inference_rejects_tampered_model(tmp_path: Path) -> None:
    value = example()
    dataset = tmp_path / "locked.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    model = tmp_path / "model"
    model.mkdir()
    weights = model / "weights.bin"
    weights.write_bytes(b"original")
    semantic_manifest = tmp_path / "semantic-manifest.json"
    semantic_manifest.write_text(
        json.dumps(
            {
                "model_tree_sha256": tree_sha256(model),
                "model_version": "semantic-test-v1",
                "temperature": 1.0,
            }
        )
    )
    weights.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="model tree"):
        infer_external(
            dataset,
            semantic_manifest,
            model,
            tmp_path / "predictions.jsonl",
            predictor=lambda _: [],
        )
