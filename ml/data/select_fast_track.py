from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ml.data.adapters.base import file_sha256
from ml.data.schema import AceDatasetExample

SELECTION_VERSION = "fast-track-selection-v1"
DEFAULT_SEED = 2026
HELD_OUT_SPLITS = ("validation", "calibration", "golden")


@dataclass(frozen=True)
class GroupCandidate:
    group_id: str
    examples: tuple[AceDatasetExample, ...]
    stratum: str
    diversity_bucket: str

    @property
    def row_count(self) -> int:
        return len(self.examples)


def _stable_hash(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def _bucket(value: int, boundaries: tuple[int, ...]) -> str:
    for boundary in boundaries:
        if value <= boundary:
            return f"lte_{boundary}"
    return f"gt_{boundaries[-1]}"


def _budget_bucket(example: AceDatasetExample) -> str:
    budgets = [
        value.amount_minor
        for value in example.mandate.constraints
        if value.type == "total_budget" and value.amount_minor
    ]
    if not budgets:
        return "missing"
    ratio = example.cart.total_amount_minor / min(budgets)
    if ratio <= 0.5:
        return "lte_0.50"
    if ratio <= 0.8:
        return "0.50_to_0.80"
    if ratio < 1.0:
        return "0.80_to_1.00"
    if ratio == 1.0:
        return "exact_1.00"
    return "gt_1.00"


def _semantic_bucket(example: AceDatasetExample) -> str:
    values = sorted({value.label.value for value in example.labels.semantic})
    return "+".join(values) if values else "UNLABELED"


def _text(example: AceDatasetExample) -> str:
    evidence = " ".join(
        value.evidence_text or value.description for value in example.cart.line_items
    )
    return f"{example.mandate.objective_text} {evidence}".strip()


def _simhash_bucket(text: str, bits: int = 8) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        return "empty"
    vector = [0] * bits
    for token, weight in Counter(tokens).items():
        digest = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        for bit in range(bits):
            vector[bit] += weight if digest & (1 << bit) else -weight
    value = sum((1 << bit) for bit, score in enumerate(vector) if score >= 0)
    return f"{value:0{bits // 4}x}"


def row_dimensions(example: AceDatasetExample) -> dict[str, str]:
    text = _text(example)
    return {
        "label_source": example.labels.label_source,
        "deviation": (
            example.labels.deviation.value
            if example.labels.deviation is not None
            else "UNLABELED"
        ),
        "semantic": _semantic_bucket(example),
        "expected_treatment": (
            example.labels.expected_treatment.value
            if example.labels.expected_treatment is not None
            else "UNLABELED"
        ),
        "transformation": example.provenance.transformation,
        "evidence_origin": example.provenance.evidence_origin.value,
        "evidence_sufficiency": example.cart.evidence_sufficiency,
        "cart_size": _bucket(len(example.cart.line_items), (1, 2, 4)),
        "budget_utilization": _budget_bucket(example),
        "text_length": _bucket(len(text), (256, 1024, 4096)),
    }


def _primary_profile(example: AceDatasetExample) -> tuple[str, ...]:
    dimensions = row_dimensions(example)
    return tuple(
        dimensions[name]
        for name in (
            "label_source",
            "deviation",
            "semantic",
            "transformation",
            "evidence_sufficiency",
            "evidence_origin",
            "text_length",
        )
    )


def _group_candidate(
    group_id: str, examples: list[AceDatasetExample]
) -> GroupCandidate:
    profiles = sorted({_primary_profile(value) for value in examples})
    diversity = sorted(
        {
            (
                row_dimensions(value)["cart_size"],
                row_dimensions(value)["budget_utilization"],
                row_dimensions(value)["text_length"],
                _simhash_bucket(_text(value)),
            )
            for value in examples
        }
    )
    return GroupCandidate(
        group_id=group_id,
        examples=tuple(sorted(examples, key=lambda value: value.identity.example_id)),
        stratum=json.dumps(profiles, separators=(",", ":")),
        diversity_bucket=json.dumps(diversity, separators=(",", ":")),
    )


def _diverse_order(
    values: list[GroupCandidate], seed: int
) -> deque[GroupCandidate]:
    by_bucket: dict[str, list[GroupCandidate]] = defaultdict(list)
    for value in values:
        by_bucket[value.diversity_bucket].append(value)
    for bucket in by_bucket.values():
        bucket.sort(key=lambda value: _stable_hash(seed, value.group_id))
    bucket_names = sorted(by_bucket, key=lambda value: _stable_hash(seed, value))
    ordered: deque[GroupCandidate] = deque()
    while any(by_bucket.values()):
        for name in bucket_names:
            if by_bucket[name]:
                ordered.append(by_bucket[name].pop(0))
    return ordered


def _dimension_counts(
    values: list[AceDatasetExample],
) -> dict[str, Counter[str]]:
    output: dict[str, Counter[str]] = defaultdict(Counter)
    for value in values:
        for name, category in row_dimensions(value).items():
            output[name][category] += 1
    return dict(output)


def _representation_report(
    full: list[AceDatasetExample], selected: list[AceDatasetExample]
) -> dict[str, Any]:
    full_counts = _dimension_counts(full)
    selected_counts = _dimension_counts(selected)
    dimensions: dict[str, Any] = {}
    missing: list[str] = []
    full_total, selected_total = len(full), len(selected)
    for name in sorted(full_counts):
        categories = sorted(set(full_counts[name]) | set(selected_counts.get(name, {})))
        total_variation = 0.0
        for category in categories:
            full_probability = full_counts[name][category] / full_total
            selected_probability = selected_counts[name][category] / selected_total
            total_variation += abs(full_probability - selected_probability)
            if full_counts[name][category] and not selected_counts[name][category]:
                missing.append(f"{name}:{category}")
        dimensions[name] = {
            "full": dict(sorted(full_counts[name].items())),
            "selected": dict(sorted(selected_counts[name].items())),
            "total_variation_distance": round(total_variation / 2, 6),
        }
    return {
        "dimensions": dimensions,
        "max_total_variation_distance": max(
            value["total_variation_distance"] for value in dimensions.values()
        ),
        "missing_categories": sorted(missing),
    }


def select_examples(
    values: list[AceDatasetExample],
    *,
    train_rows: int,
    seed: int = DEFAULT_SEED,
    max_total_variation: float = 0.08,
    require_category_coverage: bool = True,
) -> tuple[list[AceDatasetExample], dict[str, Any]]:
    if train_rows < 1:
        raise ValueError("train_rows must be positive")
    group_splits: dict[str, str] = {}
    train_by_group: dict[str, list[AceDatasetExample]] = defaultdict(list)
    held_out: list[AceDatasetExample] = []
    for value in values:
        existing = group_splits.setdefault(value.identity.group_id, value.split.name)
        if existing != value.split.name:
            raise ValueError(
                f"group {value.identity.group_id} crosses {existing} and {value.split.name}"
            )
        if value.split.name == "train":
            train_by_group[value.identity.group_id].append(value)
        elif value.split.name in HELD_OUT_SPLITS:
            held_out.append(value)
        else:
            raise ValueError(f"unsupported fast-track split: {value.split.name}")

    full_train = [value for group in train_by_group.values() for value in group]
    if train_rows > len(full_train):
        raise ValueError(
            f"requested {train_rows} train rows from only {len(full_train)} available"
        )
    candidates = [
        _group_candidate(group_id, examples)
        for group_id, examples in train_by_group.items()
    ]
    by_stratum: dict[str, list[GroupCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_stratum[candidate.stratum].append(candidate)
    queues = {
        stratum: _diverse_order(group, seed) for stratum, group in by_stratum.items()
    }
    stratum_rows = {
        stratum: sum(value.row_count for value in group)
        for stratum, group in by_stratum.items()
    }
    ideal_rows = {
        stratum: train_rows * count / len(full_train)
        for stratum, count in stratum_rows.items()
    }
    selected_groups: list[GroupCandidate] = []
    selected_by_stratum: Counter[str] = Counter()
    selected_rows = 0
    while selected_rows < train_rows:
        remaining = train_rows - selected_rows
        choices: list[tuple[float, str, GroupCandidate]] = []
        for stratum, queue in queues.items():
            candidate = next(
                (value for value in queue if value.row_count <= remaining), None
            )
            if candidate is None:
                continue
            ratio = selected_by_stratum[stratum] / max(ideal_rows[stratum], 1e-9)
            choices.append((ratio, _stable_hash(seed, stratum), candidate))
        if not choices:
            raise ValueError(
                f"group boundaries prevent an exact {train_rows}-row selection; "
                f"selected {selected_rows}"
            )
        _, _, chosen = min(choices, key=lambda value: (value[0], value[1]))
        queues[chosen.stratum].remove(chosen)
        selected_groups.append(chosen)
        selected_by_stratum[chosen.stratum] += chosen.row_count
        selected_rows += chosen.row_count

    selected_train = [
        value for group in selected_groups for value in group.examples
    ]
    representation = _representation_report(full_train, selected_train)
    if require_category_coverage and representation["missing_categories"]:
        raise ValueError(
            "fast-track selection omitted represented categories: "
            + ", ".join(representation["missing_categories"])
        )
    if representation["max_total_variation_distance"] > max_total_variation:
        raise ValueError(
            "fast-track selection exceeds total-variation gate: "
            f"{representation['max_total_variation_distance']:.6f} > "
            f"{max_total_variation:.6f}"
        )
    output = sorted(
        [*selected_train, *held_out], key=lambda value: value.identity.example_id
    )
    report = {
        "selection_version": SELECTION_VERSION,
        "seed": seed,
        "source_rows": len(values),
        "source_train_rows": len(full_train),
        "selected_train_rows": len(selected_train),
        "selected_train_groups": len(selected_groups),
        "retained_held_out_rows": len(held_out),
        "retained_held_out_splits": dict(
            sorted(Counter(value.split.name for value in held_out).items())
        ),
        # Keep the canonical manifest contract used by validate_dataset while
        # retaining output_rows as the selection-specific summary field.
        "row_count": len(output),
        "output_rows": len(output),
        "max_allowed_total_variation": max_total_variation,
        "representation": representation,
        "selected_example_ids_sha256": hashlib.sha256(
            "\n".join(sorted(value.identity.example_id for value in selected_train)).encode()
        ).hexdigest(),
    }
    return output, report


def select_file(
    dataset_path: Path,
    output_dir: Path,
    *,
    train_rows: int,
    seed: int = DEFAULT_SEED,
    max_total_variation: float = 0.08,
    source_manifest_path: Path | None = None,
) -> dict[str, Any]:
    with dataset_path.open() as source:
        values = [
            AceDatasetExample.model_validate_json(line)
            for line in source
            if line.strip()
        ]
    source_sha256 = file_sha256(dataset_path)
    if source_manifest_path is not None:
        source_manifest = json.loads(source_manifest_path.read_text())
        if source_manifest["row_count"] != len(values):
            raise ValueError("source manifest row count does not match dataset")
        if source_manifest["dataset_sha256"] != source_sha256:
            raise ValueError("source manifest checksum does not match dataset")
    selected, report = select_examples(
        values,
        train_rows=train_rows,
        seed=seed,
        max_total_variation=max_total_variation,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_output = output_dir / "ace-fast-track.jsonl"
    dataset_output.write_text(
        "".join(value.model_dump_json() + "\n" for value in selected)
    )
    manifest = {
        **report,
        "source_dataset": str(dataset_path),
        "source_dataset_sha256": source_sha256,
        "dataset": str(dataset_output),
        "dataset_sha256": file_sha256(dataset_output),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-rows", type=int, default=4_000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-total-variation", type=float, default=0.08)
    args = parser.parse_args()
    print(
        json.dumps(
            select_file(
                args.dataset,
                args.output,
                train_rows=args.train_rows,
                seed=args.seed,
                max_total_variation=args.max_total_variation,
                source_manifest_path=args.source_manifest,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
