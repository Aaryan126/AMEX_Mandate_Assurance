from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ml.semantic.checkpoints import file_sha256, keys_sha256
from ml.semantic.dataset import ID_LABELS, NliTrainingRow, load_nli_inference_rows
from ml.semantic.train_multilingual import (
    _dependencies,
    _predict,
    _probabilities,
    _release_model,
    tree_sha256,
    validate_prediction_quality,
)

Predictor = Callable[[list[NliTrainingRow]], list[list[float]]]


def _row_key(value: NliTrainingRow | dict[str, Any]) -> tuple[str, str]:
    if isinstance(value, dict):
        return str(value["example_id"]), str(value["constraint_id"])
    return value.example_id, value.constraint_id


def _validate_probability_row(value: dict[str, Any], *, line_number: int) -> None:
    probabilities = [
        value.get("contradiction"),
        value.get("neutral"),
        value.get("entailment"),
    ]
    if not all(
        isinstance(item, (int, float))
        and math.isfinite(item)
        and 0.0 <= item <= 1.0
        for item in probabilities
    ):
        raise ValueError(
            f"semantic prediction has invalid probabilities at line {line_number}"
        )
    if not math.isclose(sum(probabilities), 1.0, abs_tol=1e-9):
        raise ValueError(
            f"semantic probabilities do not sum to one at line {line_number}"
        )


def _load_existing(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    output: dict[tuple[str, str], dict[str, Any]] = {}
    with path.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            _validate_probability_row(value, line_number=line_number)
            key = _row_key(value)
            if key in output:
                raise ValueError(
                    f"duplicate semantic prediction key at line {line_number}"
                )
            output[key] = value
    return output


def _model_predictor(model_dir: Path, batch_size: int) -> Predictor:
    torch, _, _, AutoModel, AutoTokenizer = _dependencies()
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModel.from_pretrained(model_dir, local_files_only=True)
    expected_labels = {int(index): label for index, label in ID_LABELS.items()}
    actual_labels = {
        int(index): str(label) for index, label in model.config.id2label.items()
    }
    if actual_labels != expected_labels:
        raise ValueError(
            f"final semantic model label order is not canonical: {actual_labels}"
        )
    model.float()
    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    model.to(device)

    def predict(rows: list[NliTrainingRow]) -> list[list[float]]:
        try:
            return _predict(model, tokenizer, rows, batch_size=batch_size)
        finally:
            _release_model(model, tokenizer)

    return predict


def _bound_manifest(
    dataset_path: Path,
    source_predictions_path: Path,
    semantic_manifest_path: Path,
    model_dir: Path,
) -> dict[str, Any]:
    semantic_manifest = json.loads(semantic_manifest_path.read_text())
    dataset_sha256 = file_sha256(dataset_path)
    source_predictions_sha256 = file_sha256(source_predictions_path)
    model_tree_sha256 = tree_sha256(model_dir)
    if semantic_manifest.get("dataset_sha256") != dataset_sha256:
        raise ValueError("semantic manifest dataset binding does not match")
    if semantic_manifest.get("predictions_sha256") != source_predictions_sha256:
        raise ValueError("semantic manifest prediction binding does not match")
    if semantic_manifest.get("model_tree_sha256") != model_tree_sha256:
        raise ValueError("semantic manifest model-tree binding does not match")
    temperature = semantic_manifest.get("temperature")
    if not isinstance(temperature, (int, float)) or temperature <= 0:
        raise ValueError("semantic manifest temperature must be positive")
    return {
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_sha256,
        "source_predictions_path": str(source_predictions_path),
        "source_predictions_sha256": source_predictions_sha256,
        "semantic_manifest_path": str(semantic_manifest_path),
        "semantic_manifest_sha256": file_sha256(semantic_manifest_path),
        "model_path": str(model_dir),
        "model_tree_sha256": model_tree_sha256,
        "model_version": str(semantic_manifest["model_version"]),
        "temperature": float(temperature),
    }


def complete(
    dataset_path: Path,
    source_predictions_path: Path,
    semantic_manifest_path: Path,
    model_dir: Path,
    output_path: Path,
    *,
    batch_size: int = 32,
    predictor: Predictor | None = None,
) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("prediction batch size must be positive")
    binding = _bound_manifest(
        dataset_path,
        source_predictions_path,
        semantic_manifest_path,
        model_dir,
    )
    rows = load_nli_inference_rows(dataset_path)
    row_by_key = {_row_key(row): row for row in rows}
    if len(row_by_key) != len(rows):
        raise ValueError("semantic inference rows contain duplicate keys")
    existing = _load_existing(source_predictions_path)
    unexpected = set(existing) - set(row_by_key)
    if unexpected:
        raise ValueError(
            f"source semantic predictions contain {len(unexpected)} unexpected keys"
        )
    missing = [row for row in rows if _row_key(row) not in existing]
    manifest_path = output_path.with_suffix(".manifest.json")
    expected_resume = {
        **binding,
        "source_prediction_rows": len(existing),
        "inferred_rows": len(missing),
        "written": len(rows),
    }
    if output_path.is_file() and manifest_path.is_file():
        saved = json.loads(manifest_path.read_text())
        if all(saved.get(key) == value for key, value in expected_resume.items()):
            if saved.get("predictions_sha256") != file_sha256(output_path):
                raise ValueError("completed semantic predictions checksum mismatch")
            completed = _load_existing(output_path)
            if set(completed) != set(row_by_key):
                raise ValueError("completed semantic predictions key coverage mismatch")
            return {**saved, "skipped": True}

    generated: dict[tuple[str, str], dict[str, Any]] = {}
    if missing:
        predict = predictor or _model_predictor(model_dir, batch_size)
        logits = predict(missing)
        if len(logits) != len(missing):
            raise ValueError("missing-row predictions do not align with inference rows")
        if len(logits) >= 2:
            validate_prediction_quality(logits, context="unlabeled semantic completion")
        elif len(logits) == 1 and (
            len(logits[0]) != 3
            or not all(math.isfinite(value) for value in logits[0])
        ):
            raise ValueError("unlabeled semantic completion returned invalid logits")
        for row, values in zip(missing, logits, strict=True):
            probabilities = _probabilities(values, binding["temperature"])
            generated[_row_key(row)] = {
                **asdict(row),
                "label": None,
                "contradiction": probabilities[0],
                "entailment": probabilities[2],
                "neutral": probabilities[1],
                "prediction_origin": "unlabeled_inference",
                "model_version": binding["model_version"],
            }

    merged = {**existing, **generated}
    if set(merged) != set(row_by_key):
        raise ValueError(
            "completed semantic predictions do not cover every semantic constraint"
        )
    origin_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with temporary_output.open("w") as output:
            for row in rows:
                value = merged[_row_key(row)]
                origin_counts[str(value["prediction_origin"])] += 1
                split_counts[row.split] += 1
                output.write(json.dumps(value, sort_keys=True) + "\n")
        temporary_output.replace(output_path)
        key_strings = [
            f"{row.example_id}\x1f{row.constraint_id}" for row in rows
        ]
        manifest = {
            "schema_version": 1,
            **expected_resume,
            "missing_predictions": 0,
            "keys_sha256": keys_sha256(key_strings),
            "split_counts": dict(sorted(split_counts.items())),
            "prediction_origin_counts": dict(sorted(origin_counts.items())),
            "predictions_path": str(output_path),
            "predictions_sha256": file_sha256(output_path),
        }
        temporary_manifest = manifest_path.with_suffix(
            manifest_path.suffix + ".tmp"
        )
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        temporary_manifest.replace(manifest_path)
        return {**manifest, "skipped": False}
    finally:
        temporary_output.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--source-predictions", type=Path, required=True)
    parser.add_argument("--semantic-manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    print(
        json.dumps(
            complete(
                args.dataset,
                args.source_predictions,
                args.semantic_manifest,
                args.model,
                args.output,
                batch_size=args.batch_size,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
