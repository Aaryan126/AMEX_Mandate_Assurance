from __future__ import annotations

import pytest
from app.commercial_rules import evaluate_commercial_rules

from ml.features.canonical import canonical_feature_row
from tests.data.test_schema_v2 import example


@pytest.mark.parametrize(
    ("cart_amount", "fulfilled", "expected_failures", "expected_critical"),
    [
        (9_000, 0, 0, 0),
        (10_000, 0, 0, 0),
        (10_001, 0, 2, 0),
        (9_000, 1_001, 1, 1),
    ],
)
def test_offline_features_use_shared_budget_rules(
    cart_amount: int,
    fulfilled: int,
    expected_failures: int,
    expected_critical: int,
) -> None:
    value = example()
    budget = next(
        constraint
        for constraint in value.mandate.constraints
        if constraint.type == "total_budget"
    )
    budget.amount_minor = 10_000
    value.cart.line_items[0].amount_minor = cart_amount
    value.cart.total_amount_minor = cart_amount
    value.state.fulfilled_amount_minor = fulfilled
    value.state.fulfillment_count = 0
    value.mandate.max_fulfillments = 2

    signals = evaluate_commercial_rules(value.mandate, value.state, value.cart)
    features = canonical_feature_row(value, (0.0, 0.0))

    assert features["hard_fail_count"] == expected_failures
    assert features["critical_hold_count"] == expected_critical
    assert features["hard_fail_count"] == sum(
        signal.status == "FAIL" for signal in signals
    )


def test_fulfillment_boundary_is_shared_and_not_silently_safe() -> None:
    value = example()
    value.state.fulfillment_count = value.mandate.max_fulfillments

    signals = evaluate_commercial_rules(value.mandate, value.state, value.cart)
    fulfillment = next(
        signal for signal in signals if signal.rule_id == "fulfillment_limit"
    )
    features = canonical_feature_row(value, (0.0, 0.0))

    assert fulfillment.status == "FAIL"
    assert fulfillment.reason_code == "FULFILLMENT_LIMIT_EXCEEDED"
    assert features["critical_hold_count"] >= 1
