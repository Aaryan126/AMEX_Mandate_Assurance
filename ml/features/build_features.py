from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.feature_contract import FEATURE_NAMES, FEATURE_VERSION

from ml.data.schema import AceDatasetExample
from ml.features.canonical import canonical_feature_row, load_semantic_predictions


def build(dataset_path: Path, predictions_path: Path, output_path: Path) -> dict:
    predictions = load_semantic_predictions(predictions_path)
    dataset_sha256 = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    predictions_sha256 = hashlib.sha256(predictions_path.read_bytes()).hexdigest()
    predictions_manifest_path = predictions_path.with_suffix(".manifest.json")
    predictions_binding = {}
    if predictions_manifest_path.is_file():
        predictions_manifest = json.loads(predictions_manifest_path.read_text())
        if predictions_manifest.get("dataset_sha256") != dataset_sha256:
            raise ValueError("semantic predictions are not bound to this dataset")
        if predictions_manifest.get("predictions_sha256") != predictions_sha256:
            raise ValueError("semantic predictions do not match their manifest")
        predictions_binding = {
            "semantic_predictions_manifest_sha256": hashlib.sha256(
                predictions_manifest_path.read_bytes()
            ).hexdigest(),
            "semantic_model_tree_sha256": predictions_manifest.get(
                "model_tree_sha256"
            ),
            "semantic_training_manifest_sha256": predictions_manifest.get(
                "semantic_manifest_sha256"
            ),
        }
    semantic_model_versions: set[str] = set()
    with predictions_path.open() as source:
        for line in source:
            if line.strip():
                version = json.loads(line).get("model_version")
                if version:
                    semantic_model_versions.add(str(version))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"written": 0, "missing_predictions": 0}
    with dataset_path.open() as source, output_path.open("w") as output:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            example = AceDatasetExample.model_validate_json(line)
            prediction = predictions.get(example.identity.example_id)
            has_semantic_constraint = any(
                value.type == "semantic_attribute"
                for value in example.mandate.constraints
            )
            if prediction is None and has_semantic_constraint:
                counts["missing_predictions"] += 1
                continue
            prediction = prediction or (0.0, 0.0)
            output.write(
                json.dumps(canonical_feature_row(example, prediction), default=str)
                + "\n"
            )
            counts["written"] += 1
    if counts["missing_predictions"]:
        raise ValueError(
            f"semantic predictions missing for {counts['missing_predictions']} examples; refusing partial features"
        )
    manifest = {
        **counts,
        "feature_version": FEATURE_VERSION,
        "feature_names": FEATURE_NAMES,
        "dataset_sha256": dataset_sha256,
        "semantic_predictions_sha256": predictions_sha256,
        "semantic_model_versions": sorted(semantic_model_versions) or ["unknown"],
        **predictions_binding,
        "features_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--semantic-predictions", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("ml/data/generated/features-v2.jsonl")
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.dataset, args.semantic_predictions, args.output), indent=2
        )
    )


if __name__ == "__main__":
    main()
