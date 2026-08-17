from __future__ import annotations

from ml.data.transforms import assign_grouped_splits
from tests.data.test_schema_v2 import example


def test_grouped_split_assignment_hits_exact_targets() -> None:
    values = []
    for index in range(10):
        base = example().model_copy(deep=True)
        base.identity.example_id = f"ex_{index}"
        base.identity.group_id = f"group_{index}"
        values.append(base)
    assigned = assign_grouped_splits(
        values,
        {"train": 7, "validation": 1, "calibration": 1, "golden": 1},
    )
    assert {
        name: sum(value.split.name == name for value in assigned)
        for name in ("train", "validation", "calibration", "golden")
    } == {"train": 7, "validation": 1, "calibration": 1, "golden": 1}


def test_fixed_group_assignment_is_respected() -> None:
    values = []
    for index in range(4):
        base = example().model_copy(deep=True)
        base.identity.example_id = f"fixed_{index}"
        base.identity.group_id = f"fixed_group_{index}"
        values.append(base)
    assigned = assign_grouped_splits(
        values,
        {"train": 1, "validation": 1, "calibration": 1, "golden": 1},
        fixed_groups={"fixed_group_0": "golden"},
    )
    assert (
        next(
            value for value in assigned if value.identity.group_id == "fixed_group_0"
        ).split.name
        == "golden"
    )
