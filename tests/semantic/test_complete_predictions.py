from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ml.semantic.complete_predictions import complete
from ml.semantic.train_multilingual import tree_sha256
from tests.data.test_schema_v2 import example


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    labeled = example()
    unlabeled = labeled.model_copy(deep=True)
    unlabeled.identity.example_id = "example-unlabeled"
    unlabeled.identity.group_id = "group-unlabeled"
    unlabeled.labels.deviation = None
    unlabeled.labels.semantic = []
    unlabeled.labels.label_source = "unreviewed"
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        labeled.model_dump_json() + "\n" + unlabeled.model_dump_json() + "\n"
    )
    source_predictions = tmp_path / "source.jsonl"
    source_predictions.write_text(
        json.dumps(
            {
                "example_id": labeled.identity.example_id,
                "constraint_id": "waterproof",
                "contradiction": 0.1,
                "neutral": 0.2,
                "entailment": 0.7,
                "prediction_origin": "held_out",
                "model_version": "semantic-test-v1",
            }
        )
        + "\n"
    )
    model = tmp_path / "model"
    model.mkdir()
    (model / "weights.bin").write_bytes(b"test-model")
    manifest = tmp_path / "semantic-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "predictions_sha256": hashlib.sha256(
                    source_predictions.read_bytes()
                ).hexdigest(),
                "model_tree_sha256": tree_sha256(model),
                "model_version": "semantic-test-v1",
                "temperature": 2.0,
            }
        )
        + "\n"
    )
    return dataset, source_predictions, manifest, model, tmp_path / "complete.jsonl"


def test_completion_infers_only_unlabeled_rows_and_resumes(tmp_path: Path) -> None:
    dataset, source, manifest, model, output = _write_fixture(tmp_path)
    calls: list[list[str]] = []

    def predictor(rows):
        calls.append([row.example_id for row in rows])
        return [[3.0, 1.0, 0.0] for _ in rows]

    first = complete(dataset, source, manifest, model, output, predictor=predictor)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert first["skipped"] is False
    assert first["source_prediction_rows"] == 1
    assert first["inferred_rows"] == 1
    assert first["written"] == 2
    assert first["missing_predictions"] == 0
    assert calls == [["example-unlabeled"]]
    assert rows[0]["prediction_origin"] == "held_out"
    assert rows[1]["prediction_origin"] == "unlabeled_inference"
    assert rows[1]["label"] is None
    assert sum(
        rows[1][name] for name in ("contradiction", "neutral", "entailment")
    ) == pytest.approx(1.0)

    resumed = complete(
        dataset,
        source,
        manifest,
        model,
        output,
        predictor=lambda _: pytest.fail("resume must not run inference"),
    )
    assert resumed["skipped"] is True


def test_completion_rejects_tampered_source_binding(tmp_path: Path) -> None:
    dataset, source, manifest, model, output = _write_fixture(tmp_path)
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="prediction binding"):
        complete(dataset, source, manifest, model, output, predictor=lambda _: [])
