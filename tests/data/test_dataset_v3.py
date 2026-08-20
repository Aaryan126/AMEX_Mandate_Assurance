from __future__ import annotations

import pytest

from ml.data.build_dataset_v3 import (
    _assert_isolation,
    _assert_label_contract,
    _v3_labels,
)
from ml.data.schema import DatasetSplit
from ml.data.transforms import add_unrelated_item, cumulative_overspend
from tests.data.test_schema_v2 import example


def test_v3_labels_enforce_policy_for_deterministic_and_semantic_attacks() -> None:
    parent = example()
    cumulative = cumulative_overspend(parent)
    cumulative.labels = _v3_labels(cumulative, None)
    assert cumulative.labels.deterministic_outcome == ["CUMULATIVE_BUDGET_EXCEEDED"]
    assert cumulative.labels.policy_intervention_target == "HOLD"

    unrelated = add_unrelated_item(
        parent,
        product_id="extra",
        description="Unrelated headphones",
        amount_minor=0,
    )
    unrelated.labels = _v3_labels(unrelated, None)
    assert unrelated.labels.deterministic_outcome == []
    assert unrelated.labels.policy_intervention_target == "STEP_UP"
    assert "SEMANTIC_UNRELATED_ITEM" in unrelated.labels.violation_types
    _assert_label_contract([cumulative, unrelated])


def test_v3_split_isolation_rejects_shared_source_records() -> None:
    left = example().model_copy(
        deep=True,
        update={"split": DatasetSplit(name="train_fit")},
    )
    right = example().model_copy(deep=True)
    right.identity.example_id = "different"
    right.identity.group_id = "different-group"
    right.split = DatasetSplit(name="calibration")

    with pytest.raises(ValueError, match="source leakage"):
        _assert_isolation([left, right])
