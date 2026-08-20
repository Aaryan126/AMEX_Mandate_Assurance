from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ml.data import build_dataset_v4 as v4
from ml.data.schema import DatasetLabels, DatasetSplit, EvidenceOrigin
from ml.features.canonical import canonical_feature_row
from tests.data.test_schema_v2 import example


def _clone(index: int, *, deterministic: bool = False):
    value = example().model_copy(deep=True)
    value.identity.example_id = f"ex_{index}"
    value.identity.group_id = f"group_{index}"
    value.provenance.source_record_id = f"source_{index}"
    value.provenance.transformation = "near_budget_match" if deterministic else "none"
    value.provenance.evidence_origin = (
        EvidenceOrigin.HYBRID_GROUNDED
        if deterministic
        else EvidenceOrigin.REAL_PUBLIC
    )
    value.labels.label_source = (
        "deterministic_counterfactual" if deterministic else "weak_esci_mapping"
    )
    return value


def _write(path: Path, values) -> None:
    path.write_text("".join(value.model_dump_json() + "\n" for value in values))


def test_freeze_pool_excludes_consumed_relationships_and_golden(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(v4, "ROLE_TARGETS", {"train_fit": 1})
    values = [_clone(index) for index in range(4)]
    values[3].split = DatasetSplit(name="golden")
    source = tmp_path / "source.jsonl"
    consumed = tmp_path / "consumed.jsonl"
    output = tmp_path / "pool.jsonl"
    _write(source, values)
    _write(consumed, [values[0]])

    manifest = v4.freeze_pool(source, [consumed], output)

    frozen = v4._read(output)
    assert {value.identity.example_id for value in frozen} == {"ex_1", "ex_2"}
    assert manifest["row_count"] == 2
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        v4.freeze_pool(source, [consumed], output)


def test_review_selection_separates_representative_and_hard_cohorts(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        v4,
        "REVIEW_TARGETS",
        {
            "train_fit": 1,
            "calibration": 1,
            "policy_tuning": 1,
            "candidate_core_semantic": 2,
            "candidate_challenge": 2,
        },
    )
    values = [_clone(index) for index in range(12)]
    pool = tmp_path / "pool.jsonl"
    _write(pool, values)
    features = tmp_path / "features.jsonl"
    with features.open("w") as output:
        for index, value in enumerate(values):
            row = canonical_feature_row(value, (index / 20, 0.1))
            output.write(json.dumps(row) + "\n")
    model = tmp_path / "model.cbm"
    model.write_bytes(b"model")
    model_manifest = tmp_path / "model.json"
    model_manifest.write_text(
        json.dumps({"artifact_sha256": hashlib.sha256(b"model").hexdigest()})
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "candidates": {
                    "calibrated_catboost": {
                        "threshold_selection": {"threshold": 0.7}
                    }
                }
            }
        )
    )
    monkeypatch.setattr(
        v4,
        "_model_probabilities",
        lambda feature_rows, model_path: {
            example_id: index / 12
            for index, example_id in enumerate(sorted(feature_rows))
        },
    )
    queue = tmp_path / "queue.jsonl"
    ledger = tmp_path / "ledger.jsonl"

    manifest = v4.select_review_queue(
        pool, features, model, model_manifest, baseline, queue, ledger
    )

    assert manifest["rows"] == 7
    assert manifest["cohorts"] == {
        "candidate_challenge": 2,
        "candidate_core_semantic": 2,
        "development_hard": 3,
    }
    assert all(value.labels.label_source == "unreviewed" for value in v4._read(queue))


def test_development_v4_has_reliable_candidate_and_exact_roles(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        v4,
        "ROLE_TARGETS",
        {"train_fit": 4, "calibration": 2, "policy_tuning": 2, "candidate_selection": 3},
    )
    monkeypatch.setattr(
        v4,
        "REVIEW_TARGETS",
        {
            "train_fit": 1,
            "calibration": 1,
            "policy_tuning": 1,
            "candidate_core_semantic": 1,
            "candidate_challenge": 1,
        },
    )
    monkeypatch.setattr(
        v4,
        "DETERMINISTIC_TARGETS",
        {"train_fit": 1, "calibration": 1, "policy_tuning": 1, "candidate_selection": 1},
    )
    monkeypatch.setattr(v4, "WEAK_TRAIN_TARGET", 2)
    monkeypatch.setattr(v4, "TARGET_REAL_PUBLIC", 7)
    reviewed_values = [_clone(index) for index in range(5)]
    roles = [
        "train_fit",
        "calibration",
        "policy_tuning",
        "candidate_selection",
        "candidate_selection",
    ]
    cohorts = [
        "development_hard",
        "development_hard",
        "development_hard",
        "candidate_core_semantic",
        "candidate_challenge",
    ]
    for value, role in zip(reviewed_values, roles, strict=True):
        value.split = DatasetSplit(name=role)
        value.labels = DatasetLabels(
            deviation="MATCH",
            semantic=[],
            expected_treatment="APPROVE",
            label_source="llm_consensus",
            reviewer_confidence=0.9,
        )
    weak = [_clone(index) for index in range(5, 9)]
    deterministic = [_clone(index, deterministic=True) for index in range(9, 16)]
    pool = tmp_path / "pool.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    _write(pool, [*reviewed_values, *weak, *deterministic])
    _write(reviewed, reviewed_values)
    ledger.write_text(
        "".join(
            json.dumps(
                {
                    "example_id": value.identity.example_id,
                    "role": role,
                    "cohort": cohort,
                }
            )
            + "\n"
            for value, role, cohort in zip(
                reviewed_values, roles, cohorts, strict=True
            )
        )
    )

    manifest = v4.build_development_v4(pool, reviewed, ledger, tmp_path / "v4")

    assert manifest["roles"] == {
        "calibration": 2,
        "candidate_selection": 3,
        "policy_tuning": 2,
        "train_fit": 4,
    }
    built = v4._read(tmp_path / "v4" / "ace-development-v4.jsonl")
    candidate = [value for value in built if value.split.name == "candidate_selection"]
    assert all(value.labels.label_source != "weak_policy_v4" for value in candidate)
    assert manifest["evidence_origins"] == {"hybrid_grounded": 4, "real_public": 7}
