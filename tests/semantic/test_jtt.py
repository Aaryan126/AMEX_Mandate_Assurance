from __future__ import annotations

import json

import pytest

from ml.semantic.jtt import build_jtt_weights


def test_jtt_weights_only_oof_training_errors(tmp_path) -> None:
    predictions = tmp_path / "predictions.jsonl"
    rows = [
        {"example_id": "a", "constraint_id": "c", "split": "train", "label": 0, "contradiction": 0.2, "neutral": 0.7, "entailment": 0.1},
        {"example_id": "b", "constraint_id": "c", "split": "train", "label": 2, "contradiction": 0.1, "neutral": 0.1, "entailment": 0.8},
        {"example_id": "held", "constraint_id": "c", "split": "validation", "label": 0, "contradiction": 0.1, "neutral": 0.8, "entailment": 0.1},
    ]
    predictions.write_text("".join(json.dumps(row) + "\n" for row in rows))

    result = build_jtt_weights(predictions, tmp_path / "weights.json", error_weight=4)

    payload = json.loads((tmp_path / "weights.json").read_text())
    assert result["weighted_rows"] == 1
    assert payload["weights"] == {"a\x1fc": 4}
    assert "held\x1fc" not in payload["weights"]


def test_jtt_refuses_non_upweighting(tmp_path) -> None:
    with pytest.raises(ValueError, match="exceed 1"):
        build_jtt_weights(tmp_path / "missing", tmp_path / "weights", error_weight=1)
