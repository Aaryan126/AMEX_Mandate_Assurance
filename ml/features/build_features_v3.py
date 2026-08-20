from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.feature_contract_v3 import FEATURE_NAMES, FEATURE_VERSION

from ml.data.schema import AceDatasetExample
from ml.features.canonical import canonical_feature_row


def _semantic_predictions(path: Path) -> tuple[dict[str, tuple[float, float, float]], set[str]]:
    rows: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    versions: set[str] = set()
    with path.open() as source:
        for line in source:
            if not line.strip():
                continue
            value = json.loads(line)
            rows[str(value["example_id"])].append(
                (
                    float(value["contradiction"]),
                    float(value["neutral"]),
                    float(value["entailment"]),
                )
            )
            if value.get("model_version"):
                versions.add(str(value["model_version"]))
    return (
        {
            example_id: (
                max(item[0] for item in values),
                max(item[1] for item in values),
                min(item[2] for item in values),
            )
            for example_id, values in rows.items()
        },
        versions,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(dataset_path: Path, predictions_path: Path, output_path: Path) -> dict[str, Any]:
    predictions, versions = _semantic_predictions(predictions_path)
    dataset_sha256 = _sha256(dataset_path)
    predictions_sha256 = _sha256(predictions_path)
    predictions_manifest_path = predictions_path.with_suffix(".manifest.json")
    binding: dict[str, Any] = {}
    if predictions_manifest_path.is_file():
        manifest = json.loads(predictions_manifest_path.read_text())
        if manifest.get("dataset_sha256") != dataset_sha256:
            raise ValueError("semantic predictions are not bound to this dataset")
        if manifest.get("predictions_sha256") != predictions_sha256:
            raise ValueError("semantic predictions do not match their manifest")
        binding = {
            "semantic_predictions_manifest_sha256": _sha256(predictions_manifest_path),
            "semantic_model_tree_sha256": manifest.get("model_tree_sha256"),
            "semantic_training_manifest_sha256": manifest.get("semantic_manifest_sha256"),
        }
    if output_path.exists() or output_path.with_suffix(".manifest.json").exists():
        raise FileExistsError(f"refusing to overwrite features-v3 output: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    missing = 0
    written = 0
    with dataset_path.open() as source, output_path.open("x") as output:
        for line in source:
            if not line.strip():
                continue
            example = AceDatasetExample.model_validate_json(line)
            prediction = predictions.get(example.identity.example_id)
            has_semantic = any(
                constraint.type == "semantic_attribute"
                for constraint in example.mandate.constraints
            )
            if prediction is None and has_semantic:
                missing += 1
                continue
            contradiction, neutral, entailment = prediction or (0.0, 0.0, 1.0)
            row = canonical_feature_row(example, (contradiction, neutral))
            row["dataset_version"] = "ace-canonical-features-v3"
            row["semantic_entailment"] = entailment
            output.write(json.dumps(row, default=str, sort_keys=True) + "\n")
            written += 1
    if missing:
        output_path.unlink(missing_ok=True)
        raise ValueError(f"semantic predictions missing for {missing} examples")
    manifest = {
        "written": written,
        "missing_predictions": missing,
        "feature_version": FEATURE_VERSION,
        "feature_names": FEATURE_NAMES,
        "dataset_sha256": dataset_sha256,
        "semantic_predictions_sha256": predictions_sha256,
        "semantic_model_versions": sorted(versions) or ["unknown"],
        **binding,
        "features_sha256": _sha256(output_path),
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--semantic-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.dataset, args.semantic_predictions, args.output), indent=2))


if __name__ == "__main__":
    main()

