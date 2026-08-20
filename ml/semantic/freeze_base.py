from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ml.semantic.checkpoints import file_sha256, source_tree_sha256


def freeze_finetuned_base(
    source_model: Path, source_manifest: Path, output_dir: Path
) -> dict[str, Any]:
    """Copy a verified trained model into the immutable base-model contract."""
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite immutable semantic base: {output_dir}")
    manifest = json.loads(source_manifest.read_text())
    actual_tree = source_tree_sha256(source_model)
    if manifest.get("model_tree_sha256") != actual_tree:
        raise ValueError("source semantic model does not match its training manifest")
    required = {"config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"}
    if not required.issubset({path.name for path in source_model.iterdir() if path.is_file()}):
        raise ValueError("source semantic model is incomplete")
    shutil.copytree(source_model, output_dir)
    revision = hashlib.sha256(
        f"{file_sha256(source_manifest)}:{actual_tree}".encode()
    ).hexdigest()
    binding = {
        "repository": "ace/locked-semantic-v3-finetuned",
        "revision": revision,
        "tree_sha256": source_tree_sha256(output_dir),
        "source_model": str(source_model),
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": file_sha256(source_manifest),
        "production_claim_eligible": False,
    }
    (output_dir / "ace-artifact-manifest.json").write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n"
    )
    return binding


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a trained semantic model as a verified base")
    parser.add_argument("--source-model", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze_finetuned_base(args.source_model, args.source_manifest, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
