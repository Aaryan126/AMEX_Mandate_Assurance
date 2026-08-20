from __future__ import annotations

import pytest

from app.schemas import Treatment
from app.treatment_contract import (
    CRITICAL_HOLD_CODES,
    DECLARED_STEP_UP_CODES,
    POLICY_VERSION,
    policy_intervention_target,
    treatment_for_signals,
)


@pytest.mark.parametrize("reason_code", sorted(CRITICAL_HOLD_CODES))
def test_every_critical_code_holds(reason_code: str) -> None:
    assert treatment_for_signals([reason_code]) == Treatment.HOLD


@pytest.mark.parametrize("reason_code", sorted(DECLARED_STEP_UP_CODES))
def test_every_noncritical_code_steps_up(reason_code: str) -> None:
    assert treatment_for_signals([reason_code]) == Treatment.STEP_UP


def test_critical_hold_precedes_model_and_step_up_signals() -> None:
    assert treatment_for_signals(
        ["CUMULATIVE_BUDGET_EXCEEDED", "CURRENCY_MISMATCH"],
        model_escalation=True,
    ) == Treatment.HOLD


def test_model_and_unknown_failures_never_hold() -> None:
    assert treatment_for_signals([], model_escalation=True) == Treatment.STEP_UP
    assert treatment_for_signals([], has_unclassified_failure=True) == Treatment.STEP_UP
    assert treatment_for_signals([], has_not_evaluable=True) == Treatment.STEP_UP


def test_budget_and_currency_decisions_are_frozen_as_step_up() -> None:
    assert treatment_for_signals(["SINGLE_CART_BUDGET_EXCEEDED"]) == Treatment.STEP_UP
    assert treatment_for_signals(["CURRENCY_MISMATCH"]) == Treatment.STEP_UP


def test_policy_target_and_version_are_explicit() -> None:
    assert POLICY_VERSION == "policy-treatment-contract-v3"
    assert policy_intervention_target("APPROVE") == 0
    assert policy_intervention_target("STEP_UP") == 1
    assert policy_intervention_target("HOLD") == 1
