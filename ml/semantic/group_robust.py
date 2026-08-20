from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ml.data.schema import AceDatasetExample

MIN_WEIGHT = 0.50
MAX_WEIGHT = 2.50


def source_bucket(label_source: str) -> str:
    if label_source.startswith("llm_"):
        return "llm_reviewed"
    if "deterministic" in label_source:
        return "deterministic"
    return "weak_or_public"


def _group(example: AceDatasetExample) -> str:
    if len(example.labels.semantic) != 1:
        raise ValueError("Stage C group balancing requires exactly one semantic annotation per row")
    return f"{example.labels.semantic[0].label.value}|{source_bucket(example.labels.label_source)}"


def _normalized_group_weights(counts: Counter[str]) -> dict[str, float]:
    if not counts or any(value <= 0 for value in counts.values()):
        raise ValueError("group balancing requires non-empty positive group counts")
    total = sum(counts.values())
    groups = len(counts)
    raw = {group: math.sqrt(total / (groups * count)) for group, count in counts.items()}
    mean = sum(counts[group] * raw[group] for group in counts) / total
    clipped = {
        group: min(MAX_WEIGHT, max(MIN_WEIGHT, value / mean))
        for group, value in raw.items()
    }
    clipped_mean = sum(counts[group] * clipped[group] for group in counts) / total
    return {group: value / clipped_mean for group, value in clipped.items()}


def build_group_weights(dataset_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite Stage C group weights: {output_path}")
    examples: list[AceDatasetExample] = []
    with dataset_path.open() as source:
        for line in source:
            if line.strip():
                value = AceDatasetExample.model_validate_json(line)
                if value.split.name == "train":
                    examples.append(value)
    if not examples:
        raise ValueError("Stage C group balancing requires training rows")
    counts = Counter(_group(value) for value in examples)
    group_weights = _normalized_group_weights(counts)
    weights: dict[str, float] = {}
    per_group_values: dict[str, list[float]] = defaultdict(list)
    for value in examples:
        annotation = value.labels.semantic[0]
        key = f"{value.identity.example_id}\x1f{annotation.constraint_id}"
        if key in weights:
            raise ValueError("Stage C semantic corpus contains duplicate training keys")
        weight = group_weights[_group(value)]
        weights[key] = weight
        per_group_values[_group(value)].append(weight)
    weighted_mean = sum(weights.values()) / len(weights)
    if not math.isclose(weighted_mean, 1.0, rel_tol=0, abs_tol=1e-9):
        raise AssertionError("Stage C weights must preserve unit mean")
    payload = {
        "method": "label-source-group-inverse-sqrt-v1",
        "source_dataset": str(dataset_path),
        "source_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "train_rows": len(examples),
        "non_training_rows_accessed": 0,
        "candidate_rows_accessed": 0,
        "group_counts": dict(sorted(counts.items())),
        "group_weights": {key: group_weights[key] for key in sorted(group_weights)},
        "minimum_weight": min(weights.values()),
        "maximum_weight": max(weights.values()),
        "mean_weight": weighted_mean,
        "weights": dict(sorted(weights.items())),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {key: value for key, value in payload.items() if key != "weights"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build leakage-safe Stage C semantic group weights")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_group_weights(args.dataset, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
