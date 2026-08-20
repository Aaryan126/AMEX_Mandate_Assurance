from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .auth import verify_reference
from .commercial_rules import evaluate_commercial_rules
from .schemas import (
    CartEvidence,
    Mandate,
    MandateState,
    RuleResult,
    RuleStatus,
)

TRUSTED_EVIDENCE_SOURCES = {
    "SIMULATED_MERCHANT_SIGNED_CART",
    "SIMULATED_PSP_SIGNED_CART",
    "AP2_SIGNED_CART",
}


def _result(
    rule_id: str,
    status: RuleStatus,
    severity: str,
    observed: Any,
    expected: Any,
    evidence_reference: str | None,
    reason_code: str | None = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        status=status,
        severity=severity,
        observed_value=observed,
        expected_value=expected,
        evidence_reference=evidence_reference,
        reason_code=reason_code,
    )


def evaluate_rules(
    mandate: Mandate,
    state: MandateState,
    cart: CartEvidence,
    now: datetime | None = None,
) -> list[RuleResult]:
    now = now or datetime.now(UTC)
    results: list[RuleResult] = []

    proposal = mandate.model_dump(
        exclude={"authorization_reference", "authenticated_at", "status", "superseded_mandate_reference"}
    )
    from .schemas import MandateProposal

    valid_signature = verify_reference(mandate.authorization_reference, MandateProposal.model_validate(proposal))
    results.append(
        _result(
            "mandate_signature",
            RuleStatus.PASS if valid_signature else RuleStatus.FAIL,
            "critical",
            "valid" if valid_signature else "invalid",
            "valid simulated signature",
            mandate.authorization_reference,
            None if valid_signature else "MANDATE_AUTHORIZATION_INVALID",
        )
    )

    active = mandate.status == "active" and state.status == "active"
    results.append(
        _result(
            "mandate_status",
            RuleStatus.PASS if active else RuleStatus.FAIL,
            "critical",
            state.status,
            "active",
            mandate.authorization_reference,
            None if active else "MANDATE_NOT_ACTIVE",
        )
    )

    within_window = mandate.valid_from <= now <= mandate.expires_at
    results.append(
        _result(
            "mandate_window",
            RuleStatus.PASS if within_window else RuleStatus.FAIL,
            "critical",
            now.isoformat(),
            {"valid_from": mandate.valid_from.isoformat(), "expires_at": mandate.expires_at.isoformat()},
            mandate.authorization_reference,
            None if within_window else "MANDATE_EXPIRED_OR_NOT_YET_VALID",
        )
    )

    trusted = cart.evidence_trust == "trusted" and cart.evidence_source in TRUSTED_EVIDENCE_SOURCES
    results.append(
        _result(
            "trusted_evidence",
            RuleStatus.PASS if trusted else RuleStatus.NOT_EVALUABLE,
            "high",
            {"trust": cart.evidence_trust, "source": cart.evidence_source},
            sorted(TRUSTED_EVIDENCE_SOURCES),
            cart.evidence_reference,
            None if trusted else "TRUSTED_CART_EVIDENCE_MISSING",
        )
    )

    replayed = cart.cart_id in state.prior_transaction_ids
    results.append(
        _result(
            "cart_replay",
            RuleStatus.FAIL if replayed else RuleStatus.PASS,
            "critical",
            cart.cart_id,
            "previously unseen cart ID",
            cart.evidence_reference,
            "CART_REPLAY_DETECTED" if replayed else None,
        )
    )

    results.extend(
        _result(
            signal.rule_id,
            RuleStatus(signal.status),
            signal.severity,
            signal.observed_value,
            signal.expected_value,
            cart.evidence_reference,
            signal.reason_code,
        )
        for signal in evaluate_commercial_rules(mandate, state, cart)
    )
    return results
