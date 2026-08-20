from __future__ import annotations

from collections.abc import Iterable

from .schemas import Treatment

POLICY_VERSION = "policy-treatment-contract-v3"

CRITICAL_HOLD_CODES = frozenset(
    {
        "MANDATE_AUTHORIZATION_INVALID",
        "MANDATE_NOT_ACTIVE",
        "MANDATE_EXPIRED_OR_NOT_YET_VALID",
        "CART_REPLAY_DETECTED",
        "CUMULATIVE_BUDGET_EXCEEDED",
        "FULFILLMENT_LIMIT_EXCEEDED",
        "EXPLICIT_PROHIBITED_ITEM_OR_CATEGORY",
        "MERCHANT_NOT_AUTHORIZED",
    }
)

DECLARED_STEP_UP_CODES = frozenset(
    {
        "TRUSTED_CART_EVIDENCE_MISSING",
        "CURRENCY_MISMATCH",
        "SINGLE_CART_BUDGET_EXCEEDED",
        "ROUTE_EVIDENCE_MISSING",
        "ROUTE_MISMATCH",
        "TRAVEL_DATE_EVIDENCE_MISSING",
        "TRAVEL_DATE_MISMATCH",
        "REQUIRED_ATTRIBUTE_CONTRADICTED",
        "REQUIRED_ATTRIBUTE_EVIDENCE_MISSING",
        "SEMANTIC_UNRELATED_ITEM",
        "MODEL_RISK_THRESHOLD_EXCEEDED",
    }
)

LABEL_PRECEDENCE = (
    "deterministic_rule_outcome",
    "audited_semantic_outcome",
    "structured_risk_score",
    "versioned_treatment_policy",
)


def treatment_for_signals(
    reason_codes: Iterable[str],
    *,
    has_unclassified_failure: bool = False,
    has_not_evaluable: bool = False,
    model_escalation: bool = False,
) -> Treatment:
    codes = set(reason_codes)
    if codes.intersection(CRITICAL_HOLD_CODES):
        return Treatment.HOLD
    if (
        codes.intersection(DECLARED_STEP_UP_CODES)
        or has_unclassified_failure
        or has_not_evaluable
        or model_escalation
    ):
        return Treatment.STEP_UP
    return Treatment.APPROVE


def policy_intervention_target(treatment: str | Treatment) -> int:
    return int(Treatment(treatment) != Treatment.APPROVE)
