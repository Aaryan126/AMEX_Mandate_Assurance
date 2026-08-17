from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ml.data.adapters.base import file_sha256
from ml.data.schema import AceDatasetExample


def validate(path: Path, manifest_path: Path | None = None) -> dict:
    example_ids: set[str] = set()
    group_splits: dict[str, str] = {}
    counts: Counter[str] = Counter()
    with path.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            value = AceDatasetExample.model_validate_json(line)
            if value.identity.example_id in example_ids:
                raise ValueError(f"duplicate example ID at line {line_number}")
            example_ids.add(value.identity.example_id)
            existing_split = group_splits.setdefault(
                value.identity.group_id, value.split.name
            )
            if existing_split != value.split.name:
                raise ValueError(
                    f"group {value.identity.group_id} crosses {existing_split} and {value.split.name}"
                )
            constraint_ids = {item.constraint_id for item in value.mandate.constraints}
            unknown_annotations = {
                item.constraint_id for item in value.labels.semantic
            } - constraint_ids
            if unknown_annotations:
                raise ValueError(
                    f"semantic annotations reference unknown constraints at line {line_number}"
                )
            if not value.provenance.field_origins:
                raise ValueError(
                    f"field-level provenance missing at line {line_number}"
                )
            counts[f"split:{value.split.name}"] += 1
            counts[f"origin:{value.provenance.evidence_origin}"] += 1
    result = {
        "rows": len(example_ids),
        "groups": len(group_splits),
        "sha256": file_sha256(path),
        "counts": dict(sorted(counts.items())),
    }
    if manifest_path:
        manifest = json.loads(manifest_path.read_text())
        if manifest["row_count"] != result["rows"]:
            raise ValueError("manifest row count does not match dataset")
        if manifest["dataset_sha256"] != result["sha256"]:
            raise ValueError("manifest checksum does not match dataset")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.dataset, args.manifest), indent=2))


if __name__ == "__main__":
    main()
