from __future__ import annotations

import json

from ml.semantic.merge_stage_b_predictions import merge


def test_merge_only_replaces_training_overlap(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("".join(json.dumps({"identity": {"example_id": i}, "split": {"name": s}}) + "\n" for i, s in (("train", "train_fit"), ("candidate", "candidate_selection"))))
    external = tmp_path / "external.jsonl"
    external.write_text("".join(json.dumps({"example_id": i, "constraint_id": "c", "contradiction": 0.1, "neutral": 0.1, "entailment": 0.8}) + "\n" for i in ("train", "candidate")))
    external.with_suffix(".manifest.json").write_text(json.dumps({"model_tree_sha256": "model", "semantic_manifest_sha256": "manifest"}))
    oof = tmp_path / "oof.jsonl"
    oof.write_text("".join(json.dumps({"example_id": i, "constraint_id": "c", "split": "train", "contradiction": 0.8, "neutral": 0.1, "entailment": 0.1}) + "\n" for i in ("train", "candidate")))

    manifest = merge(dataset, external, oof, tmp_path / "merged.jsonl", expected_replacements=1)

    with (tmp_path / "merged.jsonl").open() as source:
        rows = [json.loads(line) for line in source]
    assert rows[0]["contradiction"] == 0.8
    assert rows[1]["contradiction"] == 0.1
    assert manifest["candidate_oof_replacements"] == 0
