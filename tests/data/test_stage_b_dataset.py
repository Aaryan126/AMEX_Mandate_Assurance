from __future__ import annotations

from collections import Counter

import pytest

from ml.data import build_stage_b_dataset as builder
from ml.data.schema import DatasetSplit, SemanticAnnotation
from tests.data.test_dataset_v4 import _clone, _write


def _reviewed(index: int, role: str):
    value = _clone(index)
    value.split = DatasetSplit(name=role)
    value.labels.label_source = "llm_consensus"
    value.labels.deviation = "MATCH"
    value.labels.expected_treatment = "APPROVE"
    value.labels.semantic = [SemanticAnnotation(
        constraint_id=value.mandate.constraints[0].constraint_id,
        label="ENTAILMENT",
    )]
    return value


def test_stage_b_dataset_excludes_v3_candidate_and_uses_fresh_deterministic(tmp_path, monkeypatch) -> None:
    v3 = [_clone(0), _clone(1)]
    v3[0].split = DatasetSplit(name="train_fit")
    v3[1].split = DatasetSplit(name="candidate_selection")
    reviewed = [
        _reviewed(10, "train_fit"),
        _reviewed(11, "calibration"),
        _reviewed(12, "policy_tuning"),
        _reviewed(13, "candidate_selection"),
    ]
    pool = [_clone(20, deterministic=True), _clone(21, deterministic=True)]
    paths = [tmp_path / name for name in ("v3.jsonl", "reviewed.jsonl", "pool.jsonl")]
    for path, values in zip(paths, (v3, reviewed, pool), strict=True): _write(path, values)
    monkeypatch.setattr(builder, "_read", lambda path: {
        "v3.jsonl": v3,
        "reviewed.jsonl": reviewed,
        "pool.jsonl": pool,
    }[path.name])
    monkeypatch.setattr(builder, "_assert_isolation", lambda values: None)
    monkeypatch.setattr(builder, "REVIEW_ROLE_COUNTS", Counter({
        "train_fit": 1,
        "calibration": 1,
        "policy_tuning": 1,
        "candidate_selection": 1,
    }))

    # Production role-count enforcement is intentionally skipped for reduced fixtures.
    manifest = builder.build_dataset(*paths, tmp_path / "stage-b.jsonl", deterministic_candidate_rows=1)

    assert manifest["v3_candidate_rows_reused"] == 0
    assert manifest["fresh_deterministic_candidate_rows"] == 1
    assert manifest["candidate_rows"] == 2
    assert manifest["candidate_sources"] == {"deterministic_policy_v4": 1, "llm_assisted_v4": 1}


def test_stage_b_dataset_refuses_bad_review_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(builder, "_read", lambda path: [])
    with pytest.raises(ValueError, match="review"):
        builder.build_dataset(tmp_path / "v3", tmp_path / "reviewed", tmp_path / "pool", tmp_path / "out")
