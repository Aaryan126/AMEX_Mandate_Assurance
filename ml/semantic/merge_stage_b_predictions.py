from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge(
    dataset_path: Path,
    external_path: Path,
    oof_path: Path,
    output_path: Path,
    *,
    expected_replacements: int = 700,
) -> dict[str, Any]:
    if output_path.exists() or output_path.with_suffix(".manifest.json").exists():
        raise FileExistsError(f"refusing to overwrite merged semantic predictions: {output_path}")
    train_ids: set[str] = set()
    with dataset_path.open() as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["split"]["name"] == "train_fit":
                train_ids.add(str(row["identity"]["example_id"]))
    oof: dict[tuple[str, str], dict[str, Any]] = {}
    with oof_path.open() as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("split") != "train":
                continue
            key = (str(row["example_id"]), str(row["constraint_id"]))
            if key in oof:
                raise ValueError("OOF predictions contain duplicate keys")
            oof[key] = row
    replacements: set[str] = set()
    rows = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with external_path.open() as source, output_path.open("x") as output:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (str(row["example_id"]), str(row["constraint_id"]))
            replacement = oof.get(key) if key[0] in train_ids else None
            if replacement is not None:
                row.update({
                    "contradiction": replacement["contradiction"],
                    "neutral": replacement["neutral"],
                    "entailment": replacement["entailment"],
                    "prediction_origin": "cross_fit_stage_b",
                })
                replacements.add(key[0])
            output.write(json.dumps(row, sort_keys=True) + "\n")
            rows += 1
    if len(replacements) != expected_replacements:
        output_path.unlink(missing_ok=True)
        raise ValueError(f"expected {expected_replacements} OOF replacements, found {len(replacements)}")
    external_manifest = json.loads(external_path.with_suffix(".manifest.json").read_text())
    manifest = {
        "dataset_sha256": _sha256(dataset_path),
        "external_predictions_sha256": _sha256(external_path),
        "oof_predictions_sha256": _sha256(oof_path),
        "predictions_sha256": _sha256(output_path),
        "written": rows,
        "oof_replaced_examples": len(replacements),
        "candidate_oof_replacements": 0,
        "model_tree_sha256": external_manifest.get("model_tree_sha256"),
        "semantic_manifest_sha256": external_manifest.get("semantic_manifest_sha256"),
    }
    output_path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Overlay leakage-safe Stage B OOF semantic predictions")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--oof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-replacements", type=int, default=700)
    args = parser.parse_args()
    print(json.dumps(merge(args.dataset, args.external, args.oof, args.output, expected_replacements=args.expected_replacements), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
