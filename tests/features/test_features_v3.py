from __future__ import annotations

import hashlib
import json

import pytest

from app.feature_contract_v3 import FEATURE_NAMES, semantic_derived_values
from ml.features.build_features_v3 import build
from ml.features.schema_v3 import feature_vector
from tests.data.test_schema_v2 import example


def test_semantic_derived_features_are_bounded_and_ordered() -> None:
    values = semantic_derived_values(
        contradiction=0.6, neutral=0.3, entailment=0.1
    )
    assert values["semantic_risk"] == pytest.approx(0.6)
    assert values["semantic_top2_margin"] == pytest.approx(0.3)
    assert values["semantic_contradiction_entailment_margin"] == pytest.approx(0.5)
    assert 0 <= values["semantic_entropy"] <= 1
    with pytest.raises(ValueError, match="sum to one"):
        semantic_derived_values(contradiction=0.6, neutral=0.3, entailment=0.2)


def test_features_v3_build_is_bound_and_refuses_overwrite(tmp_path) -> None:
    value = example()
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(
        json.dumps(
            {
                "example_id": value.identity.example_id,
                "constraint_id": "waterproof",
                "contradiction": 0.1,
                "neutral": 0.2,
                "entailment": 0.7,
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
    output = tmp_path / "features-v3.jsonl"
    manifest = build(dataset, predictions, output)
    row = json.loads(output.read_text())
    assert manifest["feature_version"] == "features-v3"
    assert manifest["feature_names"] == FEATURE_NAMES
    assert row["semantic_entailment"] == pytest.approx(0.7)
    assert len(feature_vector(row)) == len(FEATURE_NAMES)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build(dataset, predictions, output)

