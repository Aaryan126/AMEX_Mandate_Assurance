from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from .schemas import (
    Constraint,
    ConstraintType,
    InterpretationResponse,
    InterpretMandateRequest,
    MandateProposal,
    Operator,
)

_CURRENCY_CODES = {"S$": "SGD", "SGD": "SGD", "$": "USD", "USD": "USD"}
_AIRPORTS = {
    "singapore": "SIN",
    "tokyo": "TYO",
    "nrt": "NRT",
    "sydney": "SYD",
    "hong kong": "HKG",
}
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _budget(text: str) -> tuple[int, str] | None:
    match = re.search(
        r"(?:under|below|no more than|up to|maximum|max)\s*(S\$|SGD|USD|\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    symbol = (match.group(1) or "S$").upper()
    currency = _CURRENCY_CODES.get(symbol, "SGD")
    amount_minor = round(float(match.group(2).replace(",", "")) * 100)
    return amount_minor, currency


def interpret(request: InterpretMandateRequest) -> InterpretationResponse:
    text = request.objective_text
    lowered = text.lower()
    warnings: list[str] = []
    constraints: list[Constraint] = []

    budget = _budget(text)
    if budget:
        constraints.append(
            Constraint(
                constraint_id="c_budget",
                type=ConstraintType.TOTAL_BUDGET,
                operator=Operator.LTE,
                amount_minor=budget[0],
                currency=budget[1],
                source_span="total fare under the stated budget",
            )
        )
    else:
        warnings.append("No total budget was detected; confirm whether spending is intentionally uncapped.")

    for attribute in ("refundable", "economy", "nonstop"):
        if attribute in lowered:
            constraints.append(
                Constraint(
                    constraint_id=f"c_{attribute}",
                    type=ConstraintType.SEMANTIC_ATTRIBUTE,
                    operator=Operator.REQUIRED,
                    value=attribute,
                    source_span=attribute,
                )
            )

    if "do not purchase add-ons" in lowered or "no add-ons" in lowered:
        constraints.append(
            Constraint(
                constraint_id="c_no_addons",
                type=ConstraintType.PROHIBITED_ITEM,
                operator=Operator.PROHIBITED,
                value=["add-on", "gift card", "subscription", "insurance", "lounge", "baggage"],
                source_span="Do not purchase add-ons",
            )
        )

    route_match = re.search(r"from\s+([a-z ]+?)\s+to\s+([a-z ]+?)(?:,|\s+departing|\s+on)", lowered)
    if route_match:
        origin_text = route_match.group(1).strip()
        destination_text = route_match.group(2).strip()
        origin = _AIRPORTS.get(origin_text, origin_text.upper())
        destination = _AIRPORTS.get(destination_text, destination_text.upper())
        constraints.append(
            Constraint(
                constraint_id="c_route",
                type=ConstraintType.ROUTE,
                operator=Operator.EQ,
                value={"origin": origin, "destination": destination},
                source_span=route_match.group(0),
            )
        )

    dates_match = re.search(
        r"departing\s+(\d{1,2})\s+([a-z]+).*?returning\s+(\d{1,2})\s+([a-z]+)",
        lowered,
    )
    if dates_match and dates_match.group(2) in _MONTHS and dates_match.group(4) in _MONTHS:
        year = 2026  # Demo fixtures are anchored to the documented 2026 hackathon scenario.
        outbound = date(year, _MONTHS[dates_match.group(2)], int(dates_match.group(1)))
        return_date = date(year, _MONTHS[dates_match.group(4)], int(dates_match.group(3)))
        if return_date < outbound:
            return_date = return_date.replace(year=year + 1)
        constraints.append(
            Constraint(
                constraint_id="c_travel_dates",
                type=ConstraintType.TRAVEL_DATES,
                operator=Operator.EQ,
                value={"outbound_date": outbound.isoformat(), "return_date": return_date.isoformat()},
                source_span=dates_match.group(0),
            )
        )

    if not constraints:
        constraints.append(
            Constraint(
                constraint_id="c_objective",
                type=ConstraintType.SEMANTIC_ATTRIBUTE,
                operator=Operator.REQUIRED,
                value=text,
                source_span=text,
            )
        )
        warnings.append("This request is outside the curated templates and needs manual constraint review.")

    try:
        ZoneInfo(request.market_timezone)
    except Exception:
        warnings.append("Unknown market timezone; UTC was used.")

    now = datetime.now(UTC)
    proposal = MandateProposal(
        mandate_id=f"mdt_{uuid4().hex[:12]}",
        principal_id=request.principal_id,
        agent_id=request.agent_id,
        objective_text=text,
        constraints=constraints,
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=30),
        max_fulfillments=1,
    )
    return InterpretationResponse(proposal=proposal, warnings=warnings)
