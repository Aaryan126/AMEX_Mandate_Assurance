from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable

from ml.data.schema import AceDatasetExample, DatasetSplit

SPLIT_BUCKETS = (
    ("train", 70),
    ("validation", 80),
    ("calibration", 90),
    ("golden", 100),
)


def split_for_group(group_id: str, seed: int = 2026) -> str:
    value = int(hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest()[:8], 16) % 100
    for name, upper_bound in SPLIT_BUCKETS:
        if value < upper_bound:
            return name
    raise AssertionError("split bucket coverage is incomplete")


def assign_split(example: AceDatasetExample, seed: int = 2026) -> AceDatasetExample:
    group_keys = [example.identity.group_id]
    if example.identity.sequence_id:
        group_keys.append(example.identity.sequence_id)
    return example.model_copy(
        update={
            "split": DatasetSplit(
                name=split_for_group(example.identity.group_id, seed),
                grouping_keys=group_keys,
            )
        }
    )


def assign_grouped_splits(
    examples: Iterable[AceDatasetExample],
    targets: dict[str, int],
    *,
    fixed_groups: dict[str, str] | None = None,
    seed: int = 2026,
) -> list[AceDatasetExample]:
    """Assign whole groups while meeting exact row targets when singleton groups can fill gaps."""
    values = list(examples)
    if sum(targets.values()) != len(values):
        raise ValueError("split targets must equal the number of examples")
    grouped: dict[str, list[AceDatasetExample]] = defaultdict(list)
    for value in values:
        grouped[value.identity.group_id].append(value)
    fixed_groups = fixed_groups or {}
    remaining = dict(targets)
    assignments: dict[str, str] = {}
    for group_id, split in fixed_groups.items():
        if group_id not in grouped:
            raise ValueError(f"fixed split references unknown group: {group_id}")
        size = len(grouped[group_id])
        if remaining.get(split, -1) < size:
            raise ValueError(f"fixed groups exceed target for {split}")
        assignments[group_id] = split
        remaining[split] -= size

    pending = [group_id for group_id in grouped if group_id not in assignments]
    pending.sort(
        key=lambda group_id: (
            -len(grouped[group_id]),
            hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest(),
        )
    )
    for group_id in pending:
        size = len(grouped[group_id])
        candidates = [name for name, capacity in remaining.items() if capacity >= size]
        if not candidates:
            raise ValueError("group sizes cannot satisfy exact split targets")
        candidates.sort(
            key=lambda name: (
                -(remaining[name] / max(targets[name], 1)),
                hashlib.sha256(f"{seed}:{group_id}:{name}".encode()).hexdigest(),
            )
        )
        split = candidates[0]
        assignments[group_id] = split
        remaining[split] -= size
    if any(remaining.values()):
        raise ValueError(f"split assignment left unfilled targets: {remaining}")

    output: list[AceDatasetExample] = []
    for value in values:
        split = assignments[value.identity.group_id]
        keys = [value.identity.group_id]
        if value.identity.sequence_id:
            keys.append(value.identity.sequence_id)
        output.append(
            value.model_copy(
                update={"split": DatasetSplit(name=split, grouping_keys=keys)}
            )
        )
    return output
