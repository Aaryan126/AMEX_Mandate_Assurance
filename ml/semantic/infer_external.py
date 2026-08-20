from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ml.semantic.checkpoints import file_sha256, keys_sha256
from ml.semantic.complete_predictions import Predictor, _model_predictor
from ml.semantic.dataset import NliTrainingRow, load_nli_inference_rows
from ml.semantic.train_multilingual import (
    _probabilities,
    tree_sha256,
    validate_prediction_quality,
)


def _key(row: NliTrainingRow) -> tuple[str, str]:
    return row.example_id, row.constraint_id


def _load_semantic_binding(manifest_path: Path, model_dir: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    model_tree_sha256 = tree_sha256(model_dir)
    if manifest.get("model_tree_sha256") != model_tree_sha256:
        raise ValueError("semantic model tree does not match its training manifest")
    temperature = manifest.get("temperature")
    if not isinstance(temperature, (int, float)) or temperature <= 0:
        raise ValueError("semantic manifest temperature must be positive")
    model_version = manifest.get("model_version")
    if not isinstance(model_version, str) or not model_version:
        raise ValueError("semantic manifest model version is missing")
    return {
        "semantic_manifest_path": str(manifest_path),
        "semantic_manifest_sha256": file_sha256(manifest_path),
        "model_path": str(model_dir),
        "model_tree_sha256": model_tree_sha256,
        "model_version": model_version,
        "temperature": float(temperature),
    }


def infer_external(
    dataset_path: Path,
    semantic_manifest_path: Path,
    model_dir: Path,
    output_path: Path,
    *,
    batch_size: int = 32,
    predictor: Predictor | None = None,
) -> dict[str, Any]:
    """Run the frozen final semantic model over a separately bound dataset."""
    if batch_size < 1:
        raise ValueError("prediction batch size must be positive")
    binding = _load_semantic_binding(semantic_manifest_path, model_dir)
    rows = load_nli_inference_rows(dataset_path)
    if not rows:
        raise ValueError("external semantic inference requires semantic constraints")
    keys = [_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("external semantic inference contains duplicate keys")

    manifest_path = output_path.with_suffix(".manifest.json")
    expected = {
        **binding,
        "dataset_path": str(dataset_path),
        "dataset_sha256": file_sha256(dataset_path),
        "written": len(rows),
        "inference_origin": "locked_external_inference",
    }
    if output_path.is_file() and manifest_path.is_file():
        saved = json.loads(manifest_path.read_text())
        if all(saved.get(key) == value for key, value in expected.items()):
            if saved.get("predictions_sha256") != file_sha256(output_path):
                raise ValueError("external semantic predictions checksum mismatch")
            return {**saved, "skipped": True}

    predict = predictor or _model_predictor(model_dir, batch_size)
    logits = predict(rows)
    if len(logits) != len(rows):
        raise ValueError("external semantic predictions do not align with input rows")
    if len(logits) >= 2:
        validate_prediction_quality(logits, context="external semantic inference")
    elif len(logits[0]) != 3 or not all(math.isfinite(value) for value in logits[0]):
        raise ValueError("external semantic inference returned invalid logits")

    split_counts: Counter[str] = Counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with temporary_output.open("w") as output:
            for row, values in zip(rows, logits, strict=True):
                contradiction, neutral, entailment = _probabilities(
                    values, binding["temperature"]
                )
                split_counts[row.split] += 1
                output.write(
                    json.dumps(
                        {
                            **asdict(row),
                            "label": None,
                            "contradiction": contradiction,
                            "neutral": neutral,
                            "entailment": entailment,
                            "prediction_origin": expected["inference_origin"],
                            "model_version": binding["model_version"],
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        temporary_output.replace(output_path)
        manifest = {
            "schema_version": 1,
            **expected,
            "keys_sha256": keys_sha256(
                [f"{example_id}\x1f{constraint_id}" for example_id, constraint_id in keys]
            ),
            "split_counts": dict(sorted(split_counts.items())),
            "predictions_path": str(output_path),
            "predictions_sha256": file_sha256(output_path),
        }
        temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
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
    parser.add_argument("--semantic-manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    print(
        json.dumps(
            infer_external(
                args.dataset,
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
