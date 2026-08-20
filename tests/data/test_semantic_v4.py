from __future__ import annotations

from collections import Counter

import pytest

from ml.data import build_semantic_v4 as semantic_v4
from ml.data.schema import DatasetSplit, SemanticAnnotation
from tests.data.test_dataset_v4 import _clone, _write


def _labeled(index: int, split: str, label: str = "ENTAILMENT"):
    value = _clone(index)
    value.split = DatasetSplit(name=split)
    constraint_id = value.mandate.constraints[0].constraint_id
    value.labels.semantic = [SemanticAnnotation(constraint_id=constraint_id, label=label)]
    return value


def test_replay_selection_is_deterministic_and_proportional() -> None:
    values = [
        *[_labeled(index, "train", "ENTAILMENT") for index in range(6)],
        *[_labeled(index, "train", "NEUTRAL") for index in range(6, 9)],
        _labeled(9, "train", "CONTRADICTION"),
    ]

    first = semantic_v4._select_replay(values, 5)
    second = semantic_v4._select_replay(values, 5)

    assert [value.identity.example_id for value in first] == [value.identity.example_id for value in second]
    assert Counter(semantic_v4._semantic_label(value) for value in first) == {"ENTAILMENT": 3, "NEUTRAL": 1, "CONTRADICTION": 1}


def test_corpus_excludes_candidate_and_maps_roles(tmp_path, monkeypatch) -> None:
    stage_b = [
        _labeled(0, "train_fit"),
        _labeled(1, "policy_tuning", "NEUTRAL"),
        _labeled(2, "calibration", "CONTRADICTION"),
        _labeled(3, "candidate_selection"),
    ]
    stage_a = [_labeled(4, "train_fit")]
    replay = [_labeled(5, "train", "NEUTRAL"), _labeled(6, "train")]
    stage_b_path = tmp_path / "stage-b.jsonl"
    stage_a_path = tmp_path / "stage-a.jsonl"
    replay_path = tmp_path / "replay.jsonl"
    _write(stage_b_path, stage_b)
    _write(stage_a_path, stage_a)
    _write(replay_path, replay)
    monkeypatch.setattr(semantic_v4, "ROLE_COUNTS", {
        "stage_b_train": 1,
        "validation": 1,
        "calibration": 1,
        "stage_a_train": 1,
    })

    manifest = semantic_v4.build_corpus(stage_b_path, stage_a_path, replay_path, tmp_path / "corpus.jsonl", replay_target=2)

    assert manifest["split_counts"] == {"calibration": 1, "train": 4, "validation": 1}
    assert manifest["candidate_rows_excluded"] == 1
    built = semantic_v4._read(tmp_path / "corpus.jsonl")
    assert "candidate_selection" not in {value.split.name for value in built}
    assert stage_b[-1].identity.example_id not in {value.identity.example_id for value in built}


def test_corpus_refuses_wrong_role_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(semantic_v4, "_read", lambda path: [_labeled(1, "train_fit")])
    with pytest.raises(ValueError, match="role contract"):
        semantic_v4.build_corpus(tmp_path / "b", tmp_path / "a", tmp_path / "r", tmp_path / "out", replay_target=1)
