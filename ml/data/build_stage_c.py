from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ml.data.schema import AceDatasetExample

ROLE_COUNTS = {"calibration": 1_200, "policy_tuning": 1_200}
CANDIDATE_ROWS = 1_400


def build_development_roles(source_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite Stage C1 development roles: {output_path}")
    selected: list[AceDatasetExample] = []
    source_candidate_rows = 0
    with source_path.open() as source:
        for line in source:
            if not line.strip():
                continue
            value = AceDatasetExample.model_validate_json(line)
            if value.split.name == "candidate_selection":
                source_candidate_rows += 1
                continue
            if value.split.name in ROLE_COUNTS:
                selected.append(value)
    counts = Counter(value.split.name for value in selected)
    if dict(counts) != ROLE_COUNTS:
        raise ValueError(f"Stage C1 development role counts are incompatible: {dict(counts)}")
    if source_candidate_rows != CANDIDATE_ROWS:
        raise ValueError("Stage C1 source is not the locked Stage B dataset")
    example_ids = [value.identity.example_id for value in selected]
    group_ids = [value.identity.group_id for value in selected]
    if len(set(example_ids)) != len(example_ids):
        raise ValueError("Stage C1 development roles contain duplicate examples")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as output:
        for value in selected:
            output.write(value.model_dump_json() + "\n")
    manifest = {
        "dataset_version": "stage-c1-development-policy-v1",
        "source_dataset_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "rows": len(selected),
        "role_counts": dict(sorted(counts.items())),
        "candidate_rows_in_source": source_candidate_rows,
        "candidate_rows_in_output": 0,
        "candidate_labels_accessed": 0,
        "example_ids_sha256": hashlib.sha256("\n".join(sorted(example_ids)).encode()).hexdigest(),
        "group_ids_sha256": hashlib.sha256("\n".join(sorted(group_ids)).encode()).hexdigest(),
        "production_claim_eligible": False,
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate-free Stage C1 development roles")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_development_roles(args.source, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
