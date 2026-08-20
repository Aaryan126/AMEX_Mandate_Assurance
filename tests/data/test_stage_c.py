from __future__ import annotations

import json

import pytest

from ml.data import build_stage_c
from ml.data.schema import DatasetSplit
from tests.data.test_dataset_v4 import _clone


def _write(path, values) -> None:
    with path.open("w") as output:
        for value in values:
            output.write(value.model_dump_json() + "\n")


def test_development_roles_exclude_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_stage_c, "ROLE_COUNTS", {"calibration": 1, "policy_tuning": 1})
    monkeypatch.setattr(build_stage_c, "CANDIDATE_ROWS", 2)
    values = [_clone(index) for index in range(4)]
    values[0].split = DatasetSplit(name="calibration")
    values[1].split = DatasetSplit(name="policy_tuning")
    values[2].split = DatasetSplit(name="candidate_selection")
    values[3].split = DatasetSplit(name="candidate_selection")
    source = tmp_path / "source.jsonl"
    output = tmp_path / "development.jsonl"
    _write(source, values)

    manifest = build_stage_c.build_development_roles(source, output)

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert manifest["candidate_rows_in_output"] == 0
    assert manifest["candidate_labels_accessed"] == 0
    assert {row["split"]["name"] for row in rows} == {"calibration", "policy_tuning"}


def test_development_roles_refuse_overwrite(tmp_path) -> None:
    output = tmp_path / "development.jsonl"
    output.write_text("")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_stage_c.build_development_roles(tmp_path / "missing.jsonl", output)
