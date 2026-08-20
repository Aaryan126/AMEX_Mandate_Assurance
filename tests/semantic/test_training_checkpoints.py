from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.semantic.checkpoints import load_oof_logits, source_tree_sha256
from ml.semantic.dataset import NliTrainingRow, fold_for_group
from ml.semantic.train_multilingual import (
    _sample_is_finite,
    canonical_label_indices,
    finalize_semantic_run,
    prepare_training_run,
    run_semantic_fold,
    train,
    validate_prediction_quality,
)


def _rows() -> list[NliTrainingRow]:
    rows = [
        NliTrainingRow(
            example_id=f"train-{index}",
            group_id=f"group-{index}",
            constraint_id="intent",
            split="train",
            premise=f"evidence {index}",
            hypothesis="requirement",
            label=index % 3,
        )
        for index in range(20)
    ]
    assert {fold_for_group(row.group_id, 2) for row in rows} == {0, 1}
    rows.extend(
        NliTrainingRow(
            example_id=split,
            group_id=f"{split}-group",
            constraint_id="intent",
            split=split,
            premise=f"{split} evidence",
            hypothesis="requirement",
            label=2,
        )
        for split in ("validation", "calibration", "golden")
    )
    return rows


def _base_model(path: Path) -> Path:
    path.mkdir()
    (path / "model.safetensors").write_bytes(b"immutable-test-model")
    manifest = {
        "repository": "example/test-model",
        "revision": "a" * 40,
        "tree_sha256": source_tree_sha256(path),
        "model_version": "test-v1",
    }
    (path / "ace-artifact-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n"
    )
    return path


def _patch_rows(monkeypatch, rows: list[NliTrainingRow]) -> None:
    monkeypatch.setattr(
        "ml.semantic.train_multilingual.load_nli_rows", lambda _: rows
    )


def test_prepare_state_binds_dataset_base_configuration_and_groups(
    tmp_path, monkeypatch
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("immutable dataset\n")
    base_model = _base_model(tmp_path / "base")
    output = tmp_path / "output"
    rows = _rows()
    _patch_rows(monkeypatch, rows)

    first = prepare_training_run(
        dataset, base_model, output, folds=2, epochs=1
    )
    state_path = output / "training-state.json"
    state = json.loads(state_path.read_text())
    assert first["status"] == "prepared"
    assert first["folds"] == {"0": "pending", "1": "pending"}
    assert state["dataset"]["semantic_rows"] == len(rows)
    assert state["base_model"]["revision"] == "a" * 40
    assert state["configuration"]["optimizer"] == {
        "name": "AdamW",
        "epsilon": 1e-6,
        "foreach": False,
    }
    assert state["configuration"]["training_dtype"] == "float32"
    assert state["configuration"]["canonical_label_order"] == [
        "CONTRADICTION",
        "NEUTRAL",
        "ENTAILMENT",
    ]
    assert sum(value["holdout_rows"] for value in state["folds"].values()) == 20
    assert prepare_training_run(
        dataset, base_model, output, folds=2, epochs=1
    )["state_sha256"] == first["state_sha256"]

    dataset.write_text("changed dataset\n")
    with pytest.raises(ValueError, match="binding mismatch: dataset"):
        prepare_training_run(dataset, base_model, output, folds=2, epochs=1)


def test_completed_fold_is_skipped_and_tampering_is_rejected(
    tmp_path, monkeypatch
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("immutable dataset\n")
    base_model = _base_model(tmp_path / "base")
    output = tmp_path / "output"
    rows = _rows()
    _patch_rows(monkeypatch, rows)
    calls = {"train": 0}

    def fake_train(*args, **kwargs):
        calls["train"] += 1
        return object(), object()

    monkeypatch.setattr("ml.semantic.train_multilingual._train_model", fake_train)
    monkeypatch.setattr(
        "ml.semantic.train_multilingual._predict",
        lambda model, tokenizer, values, *, batch_size: [
            [float(row.label == index) for index in range(3)] for row in values
        ],
    )
    monkeypatch.setattr(
        "ml.semantic.train_multilingual._release_model", lambda *args: None
    )

    completed = run_semantic_fold(
        dataset, base_model, output, 0, folds=2, epochs=1
    )
    assert completed["status"] == "completed"
    assert completed["skipped"] is False
    assert calls["train"] == 1
    resumed = run_semantic_fold(
        dataset, base_model, output, 0, folds=2, epochs=1
    )
    assert resumed["skipped"] is True
    assert calls["train"] == 1

    run_semantic_fold(dataset, base_model, output, 1, folds=2, epochs=1)
    complete_state = json.loads((output / "training-state.json").read_text())
    assert complete_state["status"] == "ready_to_finalize"
    assert len(load_oof_logits(complete_state)) == 20
    assert calls["train"] == 2

    Path(completed["predictions_path"]).write_text("tampered\n")
    with pytest.raises(ValueError, match="checkpoint checksum mismatch"):
        run_semantic_fold(dataset, base_model, output, 0, folds=2, epochs=1)


def test_failed_fold_records_attempt_and_can_retry(tmp_path, monkeypatch) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("immutable dataset\n")
    base_model = _base_model(tmp_path / "base")
    output = tmp_path / "output"
    rows = _rows()
    _patch_rows(monkeypatch, rows)
    calls = {"train": 0}

    def flaky_train(*args, **kwargs):
        calls["train"] += 1
        if calls["train"] == 1:
            raise RuntimeError("simulated interruption")
        return object(), object()

    monkeypatch.setattr("ml.semantic.train_multilingual._train_model", flaky_train)
    monkeypatch.setattr(
        "ml.semantic.train_multilingual._predict",
        lambda model, tokenizer, values, *, batch_size: [
            [4.0 if row.label == index else 0.0 for index in range(3)]
            for row in values
        ],
    )
    monkeypatch.setattr(
        "ml.semantic.train_multilingual._release_model", lambda *args: None
    )

    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_semantic_fold(dataset, base_model, output, 1, folds=2, epochs=1)
    failed = json.loads((output / "training-state.json").read_text())["folds"]["1"]
    assert failed["status"] == "failed"
    assert failed["attempts"] == 1
    assert "simulated interruption" in failed["error"]

    completed = run_semantic_fold(
        dataset, base_model, output, 1, folds=2, epochs=1
    )
    assert completed["status"] == "completed"
    assert completed["attempts"] == 2


def test_finalize_refuses_incomplete_folds(tmp_path, monkeypatch) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("immutable dataset\n")
    base_model = _base_model(tmp_path / "base")
    output = tmp_path / "output"
    _patch_rows(monkeypatch, _rows())
    with pytest.raises(ValueError, match="all semantic fold checkpoints"):
        finalize_semantic_run(dataset, base_model, output, folds=2, epochs=1)


def test_bounded_finite_sample_detects_nonfinite_values() -> None:
    import torch

    assert _sample_is_finite(torch, torch.ones(8)) is True
    assert _sample_is_finite(torch, torch.tensor([1.0, float("nan")])) is False


def test_prediction_quality_rejects_single_class_and_constant_logits() -> None:
    with pytest.raises(ValueError, match="collapsed"):
        validate_prediction_quality(
            [[0.0, 0.0, 1.0], [0.0, 0.0, 1.1]], context="test"
        )
    result = validate_prediction_quality(
        [[3.0, 0.0, 0.0], [0.0, 3.0, 0.0]], context="test"
    )
    assert result["predicted_labels"] == [0, 1]


def test_upstream_label_order_is_mapped_to_canonical_indices() -> None:
    assert canonical_label_indices(
        {0: "entailment", 1: "neutral", 2: "contradiction"}
    ) == [2, 1, 0]
    assert canonical_label_indices(
        {0: "CONTRADICTION", 1: "NEUTRAL", 2: "ENTAILMENT"}
    ) == [0, 1, 2]
    with pytest.raises(ValueError, match="missing canonical NLI labels"):
        canonical_label_indices({0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"})


def test_full_trainer_resumes_from_completed_final_artifacts(
    tmp_path, monkeypatch
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("immutable dataset\n")
    base_model = _base_model(tmp_path / "base")
    output = tmp_path / "output"
    rows = _rows()
    _patch_rows(monkeypatch, rows)
    calls = {"train": 0}

    def fake_train(training, validation, base, model_output, **kwargs):
        calls["train"] += 1
        if model_output is not None:
            model_output.mkdir(parents=True)
            (model_output / "model.safetensors").write_bytes(b"trained-model")
        return object(), object()

    monkeypatch.setattr("ml.semantic.train_multilingual._train_model", fake_train)
    monkeypatch.setattr(
        "ml.semantic.train_multilingual._predict",
        lambda model, tokenizer, values, *, batch_size: [
            [4.0 if row.label == index else 0.0 for index in range(3)]
            for row in values
        ],
    )
    monkeypatch.setattr(
        "ml.semantic.train_multilingual._release_model", lambda *args: None
    )

    manifest = train(dataset, base_model, output, folds=2, epochs=1)
    assert manifest["rows"] == len(rows)
    assert calls["train"] == 3
    state = json.loads((output / "training-state.json").read_text())
    assert state["status"] == "completed"
    assert state["final"]["status"] == "completed"
    assert sum(1 for line in (output / "semantic-predictions.jsonl").open()) == len(
        rows
    )

    assert train(dataset, base_model, output, folds=2, epochs=1) == manifest
    assert calls["train"] == 3
