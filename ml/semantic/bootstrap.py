from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def tree_sha256(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(value for value in directory.rglob("*") if value.is_file()):
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def bootstrap(repository: str, revision: str, target: Path) -> dict[str, str]:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Install services/api[semantic] before bootstrapping NLI artifacts"
        ) from exc
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repository,
        revision=revision,
        local_dir=target,
        allow_patterns=[
            "*.json",
            "*.model",
            "model.safetensors",
            "README.md",
            "LICENSE*",
        ],
    )
    manifest = {
        "repository": repository,
        "revision": revision,
        "tree_sha256": tree_sha256(target),
        "model_version": "nli-deberta-v1",
    }
    (target / "ace-artifact-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository", default="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
    )
    parser.add_argument(
        "--revision",
        required=True,
        help="Immutable Hugging Face commit hash; mutable branch names are intentionally rejected.",
    )
    parser.add_argument(
        "--target", type=Path, default=Path("artifacts/base-models/english-nli")
    )
    args = parser.parse_args()
    if len(args.revision) < 20:
        raise SystemExit("--revision must be an immutable commit hash")
    print(json.dumps(bootstrap(args.repository, args.revision, args.target), indent=2))


if __name__ == "__main__":
    main()
