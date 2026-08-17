from __future__ import annotations

import json

import pytest

from ml.data.validate_dataset import validate
from tests.data.test_schema_v2 import example


def test_validator_rejects_group_split_leakage(tmp_path) -> None:
    first = example()
    second = first.model_copy(deep=True)
    second.identity.example_id = "example-2"
    second.split.name = "golden"
    path = tmp_path / "dataset.jsonl"
    path.write_text(first.model_dump_json() + "\n" + second.model_dump_json() + "\n")
    with pytest.raises(ValueError, match="crosses"):
        validate(path)


def test_validator_checks_manifest_hash_and_count(tmp_path) -> None:
    path = tmp_path / "dataset.jsonl"
    path.write_text(example().model_dump_json() + "\n")
    result = validate(path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"row_count": 1, "dataset_sha256": result["sha256"]})
    )
    assert validate(path, manifest)["rows"] == 1
