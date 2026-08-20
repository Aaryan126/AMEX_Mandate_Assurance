from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from ml.data import build_stage_b as stage_b
from ml.features.canonical import canonical_feature_row
from tests.data.test_dataset_v4 import _clone, _write


def _feature_rows(path: Path, values) -> None:
    with path.open("w") as output:
        for index, value in enumerate(values):
            row = canonical_feature_row(value, (index / max(len(values), 1), 0.1))
            output.write(json.dumps(row) + "\n")


def test_freeze_unused_pool_removes_all_stage_a_relationships(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(stage_b, "ROLE_STRATUM_TARGETS", {"train_fit": {"low": 1}})
    monkeypatch.setattr(stage_b, "CHALLENGE_TARGET", 1)
    values = [_clone(index) for index in range(5)]
    values[1].identity.group_id = values[0].identity.group_id
    pool = tmp_path / "pool.jsonl"
    consumed = tmp_path / "stage-a.jsonl"
    features = tmp_path / "features.jsonl"
    _write(pool, values)
    _write(consumed, [values[0]])
    _feature_rows(features, values)

    manifest = stage_b.freeze_unused_pool(
        pool, consumed, features, tmp_path / "stage-b.jsonl", tmp_path / "stage-b-features.jsonl"
    )

    assert manifest["row_count"] == 3
    assert {value.identity.example_id for value in stage_b._read(tmp_path / "stage-b.jsonl")} == {"ex_2", "ex_3", "ex_4"}
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        stage_b.freeze_unused_pool(pool, consumed, features, tmp_path / "stage-b.jsonl", tmp_path / "new-features.jsonl")


def test_selection_enforces_score_strata_in_every_role(tmp_path, monkeypatch) -> None:
    targets = {
        "train_fit": {"low": 1, "boundary": 1, "high": 1},
        "calibration": {"low": 1, "boundary": 1, "high": 1},
        "policy_tuning": {"low": 1, "boundary": 1, "high": 1},
        "candidate_selection": {"low": 1, "boundary": 1, "high": 1},
    }
    monkeypatch.setattr(stage_b, "ROLE_STRATUM_TARGETS", targets)
    monkeypatch.setattr(stage_b, "CHALLENGE_TARGET", 2)
    values = [_clone(index) for index in range(20)]
    pool = tmp_path / "pool.jsonl"
    features = tmp_path / "features.jsonl"
    _write(pool, values)
    _feature_rows(features, values)
    probabilities = {}
    for index, value in enumerate(values):
        probabilities[value.identity.example_id] = (0.1, 0.5, 0.9)[index % 3]
    monkeypatch.setattr(stage_b, "_calibrated_v3_probabilities", lambda *args: probabilities)
    model = tmp_path / "model.cbm"
    model.write_bytes(b"model")
    model_manifest = tmp_path / "model.manifest.json"
    model_manifest.write_text(json.dumps({"artifact_sha256": hashlib.sha256(b"model").hexdigest()}))
    calibrator = tmp_path / "calibrator.joblib"
    calibrator.write_bytes(b"calibrator")

    manifest = stage_b.select_review_queue(
        pool, features, model, model_manifest, calibrator, tmp_path / "queue.jsonl", tmp_path / "ledger.jsonl"
    )

    assert manifest["rows"] == 14
    assert manifest["roles"] == {"calibration": 3, "candidate_selection": 5, "policy_tuning": 3, "train_fit": 3}
    assert manifest["role_strata"] == {
        f"{role}:{stratum}": 1 for role in targets for stratum in targets[role]
    }
    queue = stage_b._read(tmp_path / "queue.jsonl")
    assert all(value.labels.label_source == "unreviewed" for value in queue)
    assert len({value.identity.group_id for value in queue}) == len(queue)


def test_score_strata_are_deterministic_quantiles() -> None:
    values = [_clone(index) for index in range(20)]
    probabilities = {value.identity.example_id: index / 20 for index, value in enumerate(values)}

    strata, bounds = stage_b._score_strata(values, probabilities)

    assert Counter(strata.values()) == {"low": 7, "boundary": 6, "high": 7}
    assert bounds == {
        "low_max": 0.3,
        "boundary_min": 0.35,
        "boundary_max": 0.6,
        "high_min": 0.65,
    }
