from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.auth import sign_proposal
from app.interpreter import interpret
from app.policy import apply_policy
from app.rules import evaluate_rules
from app.schemas import (
    InterpretMandateRequest,
    Mandate,
    MandateState,
    RuleStatus,
    Treatment,
)
from app.semantic import HeuristicSemanticScorer

from .fixtures import OBJECTIVE, cart


def mandate_and_state(max_fulfillments: int = 2):
    proposal = interpret(InterpretMandateRequest(objective_text=OBJECTIVE)).proposal.model_copy(
        update={"max_fulfillments": max_fulfillments}
    )
    authenticated_at = datetime.now(UTC)
    mandate = Mandate(
        **proposal.model_dump(),
        authorization_reference=sign_proposal(proposal, authenticated_at),
        authenticated_at=authenticated_at,
    )
    state = MandateState(
        mandate_id=mandate.mandate_id,
        current_version=1,
        status="active",
        last_updated_at=authenticated_at,
    )
    return mandate, state


def treatment_for(cart_value, state_update=None):
    mandate, state = mandate_and_state()
    if state_update:
        state = state.model_copy(update=state_update)
    rules = evaluate_rules(mandate, state, cart_value)
    semantics = HeuristicSemanticScorer().score(mandate.constraints, cart_value)
    return apply_policy(rules, semantics), rules


def test_valid_cart_approves() -> None:
    decision, rules = treatment_for(cart())
    assert decision.treatment == Treatment.APPROVE
    assert all(rule.status == RuleStatus.PASS for rule in rules)


def test_single_cart_budget_excess_steps_up() -> None:
    decision, _ = treatment_for(cart(amount_minor=96000))
    assert decision.treatment == Treatment.STEP_UP
    assert "SINGLE_CART_BUDGET_EXCEEDED" in decision.reason_codes


def test_non_refundable_cart_holds() -> None:
    decision, _ = treatment_for(cart(refundable=False))
    assert decision.treatment == Treatment.HOLD
    assert "REQUIRED_ATTRIBUTE_CONTRADICTED" in decision.reason_codes


def test_injected_add_on_holds() -> None:
    decision, _ = treatment_for(cart(extra_item="Unrelated gift card subscription"))
    assert decision.treatment == Treatment.HOLD
    assert "PROHIBITED_OR_UNRELATED_ITEM" in decision.reason_codes


def test_stateful_cumulative_breach_holds() -> None:
    decision, _ = treatment_for(
        cart(amount_minor=50000),
        {"fulfilled_amount_minor": 50000, "fulfillment_count": 1},
    )
    assert decision.treatment == Treatment.HOLD
    assert "CUMULATIVE_BUDGET_EXCEEDED" in decision.reason_codes


def test_missing_semantic_evidence_steps_up() -> None:
    decision, _ = treatment_for(cart(refundable=None))
    assert decision.treatment == Treatment.STEP_UP
    assert "REQUIRED_ATTRIBUTE_EVIDENCE_MISSING" in decision.reason_codes


def test_expired_mandate_holds() -> None:
    mandate, state = mandate_and_state()
    now = mandate.expires_at + timedelta(seconds=1)
    rules = evaluate_rules(mandate, state, cart(), now=now)
    decision = apply_policy(rules, [])
    assert decision.treatment == Treatment.HOLD
    assert "MANDATE_EXPIRED_OR_NOT_YET_VALID" in decision.reason_codes

