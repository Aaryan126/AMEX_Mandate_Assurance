from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .auth import verify_reference
from .schemas import (
    CartEvidence,
    ConstraintType,
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

    for constraint in mandate.constraints:
        if constraint.type == ConstraintType.TOTAL_BUDGET:
            if cart.currency != constraint.currency:
                results.append(
                    _result(
                        "currency_match",
                        RuleStatus.FAIL,
                        "high",
                        cart.currency,
                        constraint.currency,
                        cart.evidence_reference,
                        "CURRENCY_MISMATCH",
                    )
                )
                continue
            single_ok = cart.total_amount_minor <= (constraint.amount_minor or 0)
            results.append(
                _result(
                    "single_cart_budget",
                    RuleStatus.PASS if single_ok else RuleStatus.FAIL,
                    "medium",
                    cart.total_amount_minor,
                    constraint.amount_minor,
                    cart.evidence_reference,
                    None if single_ok else "SINGLE_CART_BUDGET_EXCEEDED",
                )
            )
            cumulative = state.fulfilled_amount_minor + cart.total_amount_minor
            cumulative_ok = cumulative <= (constraint.amount_minor or 0)
            stateful_breach = not cumulative_ok and state.fulfilled_amount_minor > 0
            results.append(
                _result(
                    "cumulative_budget",
                    RuleStatus.PASS if cumulative_ok else RuleStatus.FAIL,
                    "critical" if stateful_breach else "medium",
                    cumulative,
                    constraint.amount_minor,
                    cart.evidence_reference,
                    "CUMULATIVE_BUDGET_EXCEEDED" if stateful_breach else None,
                )
            )
        elif constraint.type == ConstraintType.PROHIBITED_ITEM:
            terms = [str(term).lower() for term in (constraint.value or [])]
            matches = [
                item.description for item in cart.line_items if any(term in item.description.lower() for term in terms)
            ]
            results.append(
                _result(
                    f"prohibited_item:{constraint.constraint_id}",
                    RuleStatus.FAIL if matches else RuleStatus.PASS,
                    "high",
                    matches,
                    {"prohibited_terms": terms},
                    cart.evidence_reference,
                    "PROHIBITED_OR_UNRELATED_ITEM" if matches else None,
                )
            )
        elif constraint.type == ConstraintType.PROHIBITED_CATEGORY:
            prohibited = {
                str(value).upper()
                for value in (constraint.value if isinstance(constraint.value, list) else [constraint.value])
                if value is not None
            }
            matched = cart.merchant_category.upper() in prohibited
            results.append(
                _result(
                    f"prohibited_category:{constraint.constraint_id}",
                    RuleStatus.FAIL if matched else RuleStatus.PASS,
                    "high",
                    cart.merchant_category,
                    {"prohibited_categories": sorted(prohibited)},
                    cart.evidence_reference,
                    "PROHIBITED_OR_UNRELATED_ITEM" if matched else None,
                )
            )
        elif constraint.type == ConstraintType.ALLOWED_MERCHANT:
            allowed = {
                str(value)
                for value in (constraint.value if isinstance(constraint.value, list) else [constraint.value])
                if value is not None
            }
            matched = cart.merchant_id in allowed
            results.append(
                _result(
                    f"allowed_merchant:{constraint.constraint_id}",
                    RuleStatus.PASS if matched else RuleStatus.FAIL,
                    "high",
                    cart.merchant_id,
                    {"allowed_merchants": sorted(allowed)},
                    cart.evidence_reference,
                    None if matched else "MERCHANT_NOT_AUTHORIZED",
                )
            )
        elif constraint.type == ConstraintType.ROUTE:
            attributes = cart.line_items[0].attributes
            expected = constraint.value or {}
            observed = {"origin": attributes.get("origin"), "destination": attributes.get("destination")}
            if not observed["origin"] or not observed["destination"]:
                status = RuleStatus.NOT_EVALUABLE
                reason = "ROUTE_EVIDENCE_MISSING"
            else:
                route_ok = all(str(observed[key]).upper() == str(expected.get(key)).upper() for key in expected)
                status = RuleStatus.PASS if route_ok else RuleStatus.FAIL
                reason = None if route_ok else "ROUTE_MISMATCH"
            results.append(
                _result(
                    "route_match",
                    status,
                    "high",
                    observed,
                    expected,
                    cart.evidence_reference,
                    reason,
                )
            )
        elif constraint.type == ConstraintType.TRAVEL_DATES:
            attributes = cart.line_items[0].attributes
            expected = constraint.value or {}
            observed = {
                "outbound_date": attributes.get("outbound_date"),
                "return_date": attributes.get("return_date"),
            }
            if not all(observed.values()):
                status = RuleStatus.NOT_EVALUABLE
                reason = "TRAVEL_DATE_EVIDENCE_MISSING"
            else:
                dates_ok = all(str(observed[key]) == str(expected.get(key)) for key in expected)
                status = RuleStatus.PASS if dates_ok else RuleStatus.FAIL
                reason = None if dates_ok else "TRAVEL_DATE_MISMATCH"
            results.append(
                _result(
                    "travel_date_match",
                    status,
                    "high",
                    observed,
                    expected,
                    cart.evidence_reference,
                    reason,
                )
            )

    fulfillment_ok = state.fulfillment_count < mandate.max_fulfillments
    results.append(
        _result(
            "fulfillment_limit",
            RuleStatus.PASS if fulfillment_ok else RuleStatus.FAIL,
            "critical",
            state.fulfillment_count + 1,
            mandate.max_fulfillments,
            cart.evidence_reference,
            None if fulfillment_ok else "FULFILLMENT_LIMIT_EXCEEDED",
        )
    )
    return results
