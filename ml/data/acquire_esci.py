from __future__ import annotations

import argparse
import json
import shutil
import ssl
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import certifi

from ml.data.adapters.base import file_sha256
from ml.data.adapters.esci import ESCI_FILES

REPOSITORY_API = "https://api.github.com/repos/amazon-science/esci-data"
SOURCE_SUBDIRECTORY = "shopping_queries_dataset"
MEDIA_ROOT = "https://media.githubusercontent.com/media/amazon-science/esci-data"
RAW_ROOT = "https://raw.githubusercontent.com/amazon-science/esci-data"
TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def resolve_revision(revision: str) -> str:
    if len(revision) >= 40 and all(
        character in "0123456789abcdef" for character in revision.lower()
    ):
        return revision.lower()
    with urllib.request.urlopen(
        f"{REPOSITORY_API}/commits/{revision}", timeout=30, context=TLS_CONTEXT
    ) as response:
        value = json.load(response)["sha"]
    if len(value) != 40:
        raise RuntimeError("GitHub did not resolve ESCI to an immutable revision")
    return value


def _download(url: str, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".part")
    offset = temporary.stat().st_size if temporary.exists() else 0
    request = urllib.request.Request(
        url, headers={"Range": f"bytes={offset}-"} if offset else {}
    )
    with (
        urllib.request.urlopen(request, timeout=60, context=TLS_CONTEXT) as response,
        temporary.open("ab" if offset and response.status == 206 else "wb") as output,
    ):
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    temporary.replace(target)


def _requires_download(
    path: Path, expected_size: int | None, expected_sha256: str | None
) -> bool:
    if not path.exists():
        return True
    with path.open("rb") as source:
        if source.read(42).startswith(b"version https://git-lfs.github.com/spec"):
            return True
    if expected_size is not None and path.stat().st_size != expected_size:
        return True
    return bool(expected_sha256 and file_sha256(path) != expected_sha256)


def source_url(revision: str, filename: str) -> str:
    # raw.githubusercontent.com returns only the Git LFS pointer for the parquet files.
    root = MEDIA_ROOT if filename.endswith(".parquet") else RAW_ROOT
    return f"{root}/{revision}/{SOURCE_SUBDIRECTORY}/{filename}"


def lfs_metadata(revision: str, filename: str) -> tuple[int | None, str | None]:
    url = f"{RAW_ROOT}/{revision}/{SOURCE_SUBDIRECTORY}/{filename}"
    with urllib.request.urlopen(url, timeout=30, context=TLS_CONTEXT) as response:
        value = response.read(1024).decode(errors="replace")
    if not value.startswith("version https://git-lfs.github.com/spec"):
        return None, None
    fields = dict(line.split(" ", 1) for line in value.splitlines() if " " in line)
    return int(fields["size"]), fields["oid"].removeprefix("sha256:")


def acquire(target: Path, revision: str = "main", minimum_free_gb: int = 15) -> dict:
    free_bytes = shutil.disk_usage(
        target.parent if target.parent.exists() else Path.cwd()
    ).free
    if free_bytes < minimum_free_gb * 1024**3:
        raise RuntimeError(
            f"ESCI acquisition requires at least {minimum_free_gb} GB free"
        )
    immutable = resolve_revision(revision)
    target.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for logical_name, filename in ESCI_FILES.items():
        path = target / filename
        expected_size, expected_sha256 = lfs_metadata(immutable, filename)
        if _requires_download(path, expected_size, expected_sha256):
            _download(source_url(immutable, filename), path)
        if expected_size is not None and path.stat().st_size != expected_size:
            raise RuntimeError(
                f"ESCI file size does not match its Git LFS pointer: {path}"
            )
        if expected_sha256 is not None and file_sha256(path) != expected_sha256:
            raise RuntimeError(
                f"ESCI checksum does not match its Git LFS pointer: {path}"
            )
        if path.suffix == ".parquet":
            with path.open("rb") as source:
                if source.read(4) != b"PAR1":
                    raise RuntimeError(f"downloaded ESCI file is not Parquet: {path}")
        checksums[logical_name] = file_sha256(path)
        sizes[logical_name] = path.stat().st_size
    manifest = {
        "dataset": "amazon-esci",
        "revision": immutable,
        "source_url": "https://github.com/amazon-science/esci-data",
        "license": "Apache-2.0",
        "acquired_at": datetime.now(UTC).isoformat(),
        "files": ESCI_FILES,
        "sha256": checksums,
        "sizes": sizes,
    }
    (target / "source-lock.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=Path("ml/data/raw/esci"))
    parser.add_argument("--revision", default="main")
    parser.add_argument("--minimum-free-gb", type=int, default=15)
    args = parser.parse_args()
    print(
        json.dumps(acquire(args.target, args.revision, args.minimum_free_gb), indent=2)
    )


if __name__ == "__main__":
    main()
