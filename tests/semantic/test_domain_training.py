from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.semantic.checkpoints import source_tree_sha256
from ml.semantic.dataset import NliTrainingRow
from ml.semantic.train_domain import (
    _validate_saved_domain_model,
    inverse_frequency_class_weights,
    prepare_domain_training,
    state_path_for,
    train_domain,
)


def _rows() -> list[NliTrainingRow]:
    output = []
    for split, count in (("train", 6), ("validation", 3)):
        output.extend(
            NliTrainingRow(
                example_id=f"{split}-{index}",
                group_id=f"{split}-group-{index}",
                constraint_id="intent",
                split=split,
                premise=f"evidence {index}",
                hypothesis="requirement",
                label=1 if index == 0 else 2,
            )
            for index in range(count)
        )
    return output


def _base_model(path: Path) -> Path:
    path.mkdir()
    (path / "model.safetensors").write_bytes(b"base-model")
    manifest = {
        "repository": "example/base-model",
        "revision": "b" * 40,
        "tree_sha256": source_tree_sha256(path),
        "model_version": "test-base",
    }
    (path / "ace-artifact-manifest.json").write_text(json.dumps(manifest) + "\n")
    return path


def _patch_rows(monkeypatch) -> None:
    monkeypatch.setattr("ml.semantic.train_domain.load_nli_rows", lambda _: _rows())
    monkeypatch.setattr(
        "ml.semantic.train_domain._predict",
        lambda model, tokenizer, rows, **kwargs: [
            [3.0 if row.label == index else 0.0 for index in range(3)]
            for row in rows
        ],
    )
    monkeypatch.setattr(
        "ml.semantic.train_domain._validate_saved_domain_model",
        lambda *args, **kwargs: None,
    )


def test_domain_checkpoint_is_bound_idempotent_and_tamper_evident(
    tmp_path, monkeypatch
) -> None:
    dataset = tmp_path / "option2.jsonl"
    dataset.write_text("immutable option2 dataset\n")
    base_model = _base_model(tmp_path / "base")
    output = tmp_path / "domain-model"
    _patch_rows(monkeypatch)
    prepared = prepare_domain_training(dataset, base_model, output)
    assert prepared["status"] == "prepared"
    assert prepared["dataset"]["training_labels"] == {"1": 1, "2": 5}
    assert prepared["configuration"]["freeze_classifier"] is True
    assert prepared["configuration"]["optimizer"] == {
        "name": "AdamW",
        "epsilon": 1e-6,
        "foreach": False,
    }
    assert prepared["configuration"]["training_dtype"] == "float32"
    assert prepared["configuration"]["canonical_label_order"] == [
        "CONTRADICTION",
        "NEUTRAL",
        "ENTAILMENT",
    ]
    assert prepared["configuration"]["class_weighting"] == (
        "inverse_frequency_observed_labels"
    )
    assert prepared["configuration"]["class_weights"] == [0.0, 3.0, 0.6]
    assert not output.exists()

    calls = {"train": 0}

    def fake_train(training, validation, base, model_output, **kwargs):
        calls["train"] += 1
        assert kwargs["freeze_classifier"] is True
        assert kwargs["class_weights"] == [0.0, 3.0, 0.6]
        model_output.mkdir(parents=True)
        (model_output / "model.safetensors").write_bytes(b"adapted-model")
        return object(), object()

    monkeypatch.setattr("ml.semantic.train_domain._train_model", fake_train)
    monkeypatch.setattr("ml.semantic.train_domain._release_model", lambda *args: None)
    manifest = train_domain(dataset, base_model, output)
    assert manifest["model_version"] == "english-nli-option2-domain-v3"
    assert calls["train"] == 1
    state = json.loads(state_path_for(output).read_text())
    assert state["status"] == "completed"
    assert train_domain(dataset, base_model, output) == manifest
    assert calls["train"] == 1

    (output / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="tree checksum mismatch"):
        prepare_domain_training(dataset, base_model, output)


def test_domain_training_failure_is_recorded_and_retryable(tmp_path, monkeypatch) -> None:
    dataset = tmp_path / "option2.jsonl"
    dataset.write_text("immutable option2 dataset\n")
    base_model = _base_model(tmp_path / "base")
    output = tmp_path / "domain-model"
    _patch_rows(monkeypatch)
    calls = {"train": 0}

    def flaky_train(training, validation, base, model_output, **kwargs):
        calls["train"] += 1
        if calls["train"] == 1:
            raise RuntimeError("simulated domain interruption")
        model_output.mkdir(parents=True)
        (model_output / "model.safetensors").write_bytes(b"adapted-model")
        return object(), object()

    monkeypatch.setattr("ml.semantic.train_domain._train_model", flaky_train)
    monkeypatch.setattr("ml.semantic.train_domain._release_model", lambda *args: None)
    with pytest.raises(RuntimeError, match="simulated domain interruption"):
        train_domain(dataset, base_model, output)
    failed = json.loads(state_path_for(output).read_text())
    assert failed["status"] == "failed"
    assert failed["attempts"] == 1

    train_domain(dataset, base_model, output)
    completed = json.loads(state_path_for(output).read_text())
    assert completed["status"] == "completed"
    assert completed["attempts"] == 2


def test_domain_training_requires_frozen_classifier(tmp_path, monkeypatch) -> None:
    dataset = tmp_path / "option2.jsonl"
    dataset.write_text("immutable option2 dataset\n")
    base_model = _base_model(tmp_path / "base")
    _patch_rows(monkeypatch)
    with pytest.raises(ValueError, match="requires a frozen classifier"):
        prepare_domain_training(
            dataset, base_model, tmp_path / "output", freeze_classifier=False
        )


def test_inverse_frequency_weights_balance_observed_classes() -> None:
    weights = inverse_frequency_class_weights(_rows()[:6])
    assert weights == [0.0, 3.0, 0.6]


def test_saved_domain_model_rejects_nonfinite_and_changed_classifier(tmp_path) -> None:
    import torch
    from safetensors.torch import save_file

    base = tmp_path / "base-weights"
    output = tmp_path / "output-weights"
    base.mkdir()
    output.mkdir()
    (base / "config.json").write_text(
        json.dumps(
            {
                "id2label": {
                    "0": "CONTRADICTION",
                    "1": "NEUTRAL",
                    "2": "ENTAILMENT",
                }
            }
        )
    )
    tensors = {
        "classifier.bias": torch.tensor([0.1, 0.2, 0.3]),
        "classifier.weight": torch.arange(6, dtype=torch.float32).reshape(3, 2),
        "deberta.encoder.weight": torch.ones(2, 2),
    }
    save_file(tensors, base / "model.safetensors")
    save_file(tensors, output / "model.safetensors")
    _validate_saved_domain_model(base, output)

    save_file(
        {**tensors, "deberta.encoder.weight": torch.tensor([[float("nan"), 1.0], [1.0, 1.0]])},
        output / "model.safetensors",
    )
    with pytest.raises(FloatingPointError, match="non-finite tensor"):
        _validate_saved_domain_model(base, output)

    save_file(
        {**tensors, "classifier.bias": torch.tensor([0.1, 0.2, 0.4])},
        output / "model.safetensors",
    )
    with pytest.raises(ValueError, match="frozen classifier tensor changed"):
        _validate_saved_domain_model(base, output)
