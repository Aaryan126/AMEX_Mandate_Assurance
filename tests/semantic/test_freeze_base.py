from __future__ import annotations

import json

import pytest

from ml.semantic.checkpoints import source_tree_sha256
from ml.semantic.freeze_base import freeze_finetuned_base


def test_freeze_finetuned_base_binds_verified_tree(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for name in ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"):
        (source / name).write_text(name)
    source_manifest = tmp_path / "manifest.json"
    source_manifest.write_text(json.dumps({"model_tree_sha256": source_tree_sha256(source)}))

    binding = freeze_finetuned_base(source, source_manifest, tmp_path / "base")

    assert binding["tree_sha256"] == source_tree_sha256(tmp_path / "base")
    assert len(binding["revision"]) == 64
    assert (tmp_path / "base" / "ace-artifact-manifest.json").exists()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freeze_finetuned_base(source, source_manifest, tmp_path / "base")


def test_freeze_finetuned_base_rejects_tampering(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.json").write_text("changed")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"model_tree_sha256": "bad"}))

    with pytest.raises(ValueError, match="does not match"):
        freeze_finetuned_base(source, manifest, tmp_path / "base")
