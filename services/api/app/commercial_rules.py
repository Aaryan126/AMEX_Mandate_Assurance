from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommercialRuleSignal:
    rule_id: str
    status: str
    severity: str
    observed_value: Any
    expected_value: Any
    reason_code: str | None = None


def _constraint_type(constraint: Any) -> str:
    value = constraint.type
    return str(getattr(value, "value", value))


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def evaluate_commercial_rules(
    mandate: Any, state: Any, cart: Any
) -> list[CommercialRuleSignal]:
    """Evaluate shared observable commercial/state rules for API and offline data."""
    results: list[CommercialRuleSignal] = []
    for constraint in mandate.constraints:
        kind = _constraint_type(constraint)
        if kind == "total_budget":
            if cart.currency != constraint.currency:
                results.append(
                    CommercialRuleSignal(
                        "currency_match",
                        "FAIL",
                        "high",
                        cart.currency,
                        constraint.currency,
                        "CURRENCY_MISMATCH",
                    )
                )
                continue
            budget = int(constraint.amount_minor or 0)
            single_ok = cart.total_amount_minor <= budget
            results.append(
                CommercialRuleSignal(
                    "single_cart_budget",
                    "PASS" if single_ok else "FAIL",
                    "medium",
                    cart.total_amount_minor,
                    budget,
                    None if single_ok else "SINGLE_CART_BUDGET_EXCEEDED",
                )
            )
            cumulative = state.fulfilled_amount_minor + cart.total_amount_minor
            cumulative_ok = cumulative <= budget
            stateful_breach = not cumulative_ok and state.fulfilled_amount_minor > 0
            results.append(
                CommercialRuleSignal(
                    "cumulative_budget",
                    "PASS" if cumulative_ok else "FAIL",
                    "critical" if stateful_breach else "medium",
                    cumulative,
                    budget,
                    "CUMULATIVE_BUDGET_EXCEEDED" if stateful_breach else None,
                )
            )
        elif kind == "prohibited_item":
            terms = [str(term).lower() for term in _values(constraint.value)]
            matches = [
                item.description
                for item in cart.line_items
                if any(term in item.description.lower() for term in terms)
            ]
            results.append(
                CommercialRuleSignal(
                    f"prohibited_item:{constraint.constraint_id}",
                    "FAIL" if matches else "PASS",
                    "critical",
                    matches,
                    {"prohibited_terms": terms},
                    "EXPLICIT_PROHIBITED_ITEM_OR_CATEGORY" if matches else None,
                )
            )
        elif kind == "prohibited_category":
            prohibited = {str(value).upper() for value in _values(constraint.value)}
            matched = cart.merchant_category.upper() in prohibited
            results.append(
                CommercialRuleSignal(
                    f"prohibited_category:{constraint.constraint_id}",
                    "FAIL" if matched else "PASS",
                    "critical",
                    cart.merchant_category,
                    {"prohibited_categories": sorted(prohibited)},
                    "EXPLICIT_PROHIBITED_ITEM_OR_CATEGORY" if matched else None,
                )
            )
        elif kind == "allowed_merchant":
            allowed = {str(value) for value in _values(constraint.value)}
            matched = cart.merchant_id in allowed
            results.append(
                CommercialRuleSignal(
                    f"allowed_merchant:{constraint.constraint_id}",
                    "PASS" if matched else "FAIL",
                    "critical",
                    cart.merchant_id,
                    {"allowed_merchants": sorted(allowed)},
                    None if matched else "MERCHANT_NOT_AUTHORIZED",
                )
            )
        elif kind == "route":
            attributes = cart.line_items[0].attributes
            expected = constraint.value or {}
            observed = {
                "origin": attributes.get("origin"),
                "destination": attributes.get("destination"),
            }
            if not observed["origin"] or not observed["destination"]:
                status, reason = "NOT_EVALUABLE", "ROUTE_EVIDENCE_MISSING"
            else:
                matches = all(
                    str(observed[key]).upper() == str(expected.get(key)).upper()
                    for key in expected
                )
                status, reason = (
                    ("PASS", None) if matches else ("FAIL", "ROUTE_MISMATCH")
                )
            results.append(
                CommercialRuleSignal(
                    "route_match", status, "high", observed, expected, reason
                )
            )
        elif kind == "travel_dates":
            attributes = cart.line_items[0].attributes
            expected = constraint.value or {}
            observed = {
                "outbound_date": attributes.get("outbound_date"),
                "return_date": attributes.get("return_date"),
            }
            if not all(observed.values()):
                status, reason = "NOT_EVALUABLE", "TRAVEL_DATE_EVIDENCE_MISSING"
            else:
                matches = all(
                    str(observed[key]) == str(expected.get(key)) for key in expected
                )
                status, reason = (
                    ("PASS", None)
                    if matches
                    else ("FAIL", "TRAVEL_DATE_MISMATCH")
                )
            results.append(
                CommercialRuleSignal(
                    "travel_date_match", status, "high", observed, expected, reason
                )
            )

    fulfillment_ok = state.fulfillment_count < mandate.max_fulfillments
    results.append(
        CommercialRuleSignal(
            "fulfillment_limit",
            "PASS" if fulfillment_ok else "FAIL",
            "critical",
            state.fulfillment_count + 1,
            mandate.max_fulfillments,
            None if fulfillment_ok else "FULFILLMENT_LIMIT_EXCEEDED",
        )
    )
    return results
