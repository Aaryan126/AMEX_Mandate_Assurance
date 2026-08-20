from __future__ import annotations

import json

import pytest

from ml.data.schema import AceDatasetExample, SemanticAnnotation
from ml.semantic.group_robust import build_group_weights, source_bucket
from tests.data.test_dataset_v4 import _clone


def _write(path, values) -> None:
    with path.open("w") as output:
        for value in values:
            output.write(value.model_dump_json() + "\n")


def test_source_bucket_separates_review_quality() -> None:
    assert source_bucket("llm_consensus") == "llm_reviewed"
    assert source_bucket("llm_adjudicated") == "llm_reviewed"
    assert source_bucket("deterministic_counterfactual") == "deterministic"
    assert source_bucket("weak_esci_mapping") == "weak_or_public"


def test_group_weights_only_use_training_rows_and_preserve_unit_mean(tmp_path) -> None:
    values: list[AceDatasetExample] = []
    for index in range(8):
        value = _clone(index)
        value.split.name = "train" if index < 6 else "candidate_selection"
        value.labels.label_source = "llm_consensus" if index < 2 else "weak_esci_mapping"
        value.labels.semantic = [
            SemanticAnnotation(constraint_id="c_product_intent", label="ENTAILMENT")
        ]
        values.append(value)
    dataset = tmp_path / "semantic.jsonl"
    output = tmp_path / "weights.json"
    _write(dataset, values)

    manifest = build_group_weights(dataset, output)
    payload = json.loads(output.read_text())

    assert manifest["train_rows"] == 6
    assert manifest["candidate_rows_accessed"] == 0
    assert len(payload["weights"]) == 6
    assert sum(payload["weights"].values()) / 6 == pytest.approx(1.0)
    assert all(f"ex_{index}" not in " ".join(payload["weights"]) for index in (6, 7))


def test_group_weights_refuse_overwrite(tmp_path) -> None:
    value = _clone(0)
    value.split.name = "train"
    value.labels.semantic = [
        SemanticAnnotation(constraint_id="c_product_intent", label="ENTAILMENT")
    ]
    dataset = tmp_path / "semantic.jsonl"
    output = tmp_path / "weights.json"
    _write(dataset, [value])
    build_group_weights(dataset, output)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_group_weights(dataset, output)
