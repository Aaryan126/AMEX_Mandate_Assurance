from __future__ import annotations

import json

from ml.features.build_features import build
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
    output = tmp_path / "features.jsonl"
    manifest = build(dataset, predictions, output)
    row = json.loads(output.read_text())
    assert manifest["written"] == 1
    assert manifest["missing_predictions"] == 0
    assert manifest["semantic_model_versions"] == ["semantic-test-v1"]
    assert row["semantic_contradiction"] == 0.1
    assert row["semantic_neutral"] == 0.1
    assert row["seed_id"] == value.identity.group_id
