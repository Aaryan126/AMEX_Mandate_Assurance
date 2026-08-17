from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas import (
    CartEvidence,
    Constraint,
    LineItem,
    Mandate,
    MandateState,
    RuleResult,
    RuleStatus,
    SemanticResult,
)
from app.structured import runtime_features

from ml.features.schema import compute_features


def test_offline_and_runtime_feature_contracts_are_identical() -> None:
    now = datetime.now(UTC)
    mandate = Mandate(
        mandate_id="mandate-1",
        principal_id="principal-1",
        agent_id="agent-1",
        objective_text="Purchase a suitable item within the approved budget.",
        constraints=[
            Constraint(
                constraint_id="budget",
                type="total_budget",
                operator="lte",
                amount_minor=10_000,
                currency="USD",
            )
        ],
        valid_from=now - timedelta(days=1),
        expires_at=now + timedelta(days=1),
        max_fulfillments=2,
        authorization_reference="test-reference",
        authenticated_at=now,
    )
    state = MandateState(
        mandate_id="mandate-1",
        current_version=1,
        status="active",
        fulfilled_amount_minor=2_000,
        fulfillment_count=1,
        last_updated_at=now,
    )
    cart = CartEvidence(
        cart_id="cart-1",
        merchant_id="merchant-1",
        merchant_category="RETAIL",
        evidence_source="SIMULATED_MERCHANT_SIGNED_CART",
        evidence_trust="trusted",
        currency="USD",
        total_amount_minor=9_000,
        line_items=[
            LineItem(
                line_item_id="line-1",
                description="Requested item",
                quantity=1,
                amount_minor=9_000,
            )
        ],
        created_at=now,
        evidence_reference="evidence-1",
    )
    rules = [
        RuleResult(rule_id="pass", status=RuleStatus.PASS, severity="low"),
        RuleResult(
            rule_id="unknown", status=RuleStatus.NOT_EVALUABLE, severity="medium"
        ),
    ]
    semantics = [
        SemanticResult(
            constraint_id="semantic-1",
            contradiction=0.2,
            entailment=0.3,
            neutral=0.5,
            evidence_reference="evidence-1",
        )
    ]
    serving = runtime_features(mandate, state, cart, rules, semantics)
    offline = compute_features(
        {
            "budget_minor": 10_000,
            "cart_amount_minor": 9_000,
            "fulfilled_amount_minor": 2_000,
            "fulfillment_count": 1,
            "max_fulfillments": 2,
            "line_item_count": 1,
            "missing_evidence_count": 1,
            "semantic_contradiction": 0.2,
            "semantic_neutral": 0.5,
            "hard_fail_count": 0,
            "soft_warning_count": 1,
            "currency": "USD",
            "cart_currency": "USD",
            "category_mismatch": False,
            "domain": "retail",
            "merchant_category": "RETAIL",
            "cart_category": "RETAIL",
            "evidence_sufficiency": "ambiguous",
        }
    )
    assert offline == serving
