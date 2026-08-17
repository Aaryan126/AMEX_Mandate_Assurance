from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ml.data.schema import AceDatasetExample


class AdapterError(RuntimeError):
    pass


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    version: str
    source_url: str
    license: str
    files: dict[str, str]
    required_columns: dict[str, list[str]]
    sha256: dict[str, str] = Field(default_factory=dict)


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SourceAdapter(ABC):
    manifest: SourceManifest

    @abstractmethod
    def validate_source(self, source_dir: Path) -> None:
        """Reject missing, corrupt, or structurally incompatible source data."""

    @abstractmethod
    def iter_records(self, source_dir: Path) -> Iterator[dict[str, Any]]:
        """Yield normalized source records without ACE-specific labels."""

    @abstractmethod
    def normalize(self, record: dict[str, Any]) -> Iterable[AceDatasetExample]:
        """Convert one source record into one or more canonical ACE examples."""
