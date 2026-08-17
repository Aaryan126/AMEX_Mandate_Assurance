from __future__ import annotations

TEMPLATES = {
    "MANDATE_AUTHORIZATION_INVALID": "The mandate authorization could not be verified.",
    "MANDATE_NOT_ACTIVE": "This mandate is no longer active.",
    "MANDATE_EXPIRED_OR_NOT_YET_VALID": "This purchase is outside the mandate's valid time window.",
    "TRUSTED_CART_EVIDENCE_MISSING": "Trusted merchant evidence is not available for this cart.",
    "CART_REPLAY_DETECTED": "This cart has already been processed under the mandate.",
    "CURRENCY_MISMATCH": "The cart currency does not match the authorized currency.",
    "SINGLE_CART_BUDGET_EXCEEDED": "The proposed purchase exceeds the authorized transaction budget.",
    "CUMULATIVE_BUDGET_EXCEEDED": "This purchase would exceed the mandate's remaining total budget.",
    "PROHIBITED_OR_UNRELATED_ITEM": "The cart contains an item that the mandate prohibits.",
    "ROUTE_EVIDENCE_MISSING": "The merchant evidence does not establish the required route.",
    "ROUTE_MISMATCH": "The itinerary route does not match the authorized route.",
    "TRAVEL_DATE_EVIDENCE_MISSING": "The merchant evidence does not establish the required travel dates.",
    "TRAVEL_DATE_MISMATCH": "The itinerary dates do not match the authorized travel dates.",
    "FULFILLMENT_LIMIT_EXCEEDED": "The mandate has already reached its fulfillment limit.",
    "REQUIRED_ATTRIBUTE_CONTRADICTED": "Trusted merchant evidence contradicts a required purchase attribute.",
    "REQUIRED_ATTRIBUTE_EVIDENCE_MISSING": "The cart does not provide enough evidence for a required attribute.",
}


def explain(reason_codes: list[str]) -> tuple[str, str]:
    if not reason_codes:
        return (
            "The proposed purchase matches the confirmed mandate.",
            "No blocking or uncertainty reason codes were produced.",
        )
    messages = [TEMPLATES[code] for code in reason_codes if code in TEMPLATES]
    if not messages:
        messages = ["The purchase needs additional review."]
    card_member = " ".join(messages[:2])
    reviewer = " ".join(f"{code}: {TEMPLATES.get(code, 'Review required.')}" for code in reason_codes)
    return card_member, reviewer
