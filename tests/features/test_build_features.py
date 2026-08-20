from __future__ import annotations

import hashlib
import json

import pytest

from ml.features.build_features import build
from ml.tabular.train_catboost import load_rows, validate_feature_dataset
from tests.data.test_schema_v2 import example


def test_feature_build_requires_and_binds_semantic_predictions(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    value = example()
    dataset.write_text(value.model_dump_json() + "\n")
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(
        json.dumps(
            {
                "example_id": value.identity.example_id,
                "constraint_id": "waterproof",
                "contradiction": 0.1,
                "entailment": 0.8,
                "neutral": 0.1,
                "model_version": "semantic-test-v1",
            }
        )
        + "\n"
    )
    predictions.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "predictions_sha256": hashlib.sha256(
                    predictions.read_bytes()
                ).hexdigest(),
                "model_tree_sha256": "a" * 64,
                "semantic_manifest_sha256": "b" * 64,
            }
        )
    )
    output = tmp_path / "features.jsonl"
    manifest = build(dataset, predictions, output)
    row = json.loads(output.read_text())
    assert manifest["written"] == 1
    assert manifest["missing_predictions"] == 0
    assert manifest["semantic_model_versions"] == ["semantic-test-v1"]
    assert manifest["semantic_model_tree_sha256"] == "a" * 64
    assert manifest["semantic_training_manifest_sha256"] == "b" * 64
    assert row["semantic_contradiction"] == 0.1
    assert row["semantic_neutral"] == 0.1
    assert row["seed_id"] == value.identity.group_id
    validated = validate_feature_dataset(output, load_rows(output))
    assert validated["features_sha256"] == manifest["features_sha256"]

    output.write_text(output.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum"):
        validate_feature_dataset(output, load_rows(output))
