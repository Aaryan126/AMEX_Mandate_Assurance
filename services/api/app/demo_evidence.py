from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from .evidence_auth import issue_signed_cart
from .schemas import CartEvidence, LineItem

DemoScenario = Literal["valid", "budget", "semantic", "injected", "stateful", "uncertain"]


def _flight_item(
    key: str,
    amount_minor: int,
    *,
    refundable: bool | None,
    evidence_text: str,
) -> LineItem:
    attributes: dict[str, object] = {
        "cabin": "economy",
        "stops": 0,
        "origin": "SIN",
        "destination": "TYO",
        "outbound_date": "2026-09-07",
        "return_date": "2026-09-10",
    }
    if refundable is not None:
        attributes["refundable"] = refundable
    description = (
        "Refundable nonstop economy airfare SIN to TYO"
        if refundable is True
        else "Non-refundable nonstop economy airfare SIN to TYO"
        if refundable is False
        else "Nonstop economy airfare SIN to TYO"
    )
    return LineItem(
        line_item_id=f"li_{key}_flight",
        description=description,
        evidence_text=evidence_text,
        quantity=1,
        amount_minor=amount_minor,
        attributes=attributes,
    )


def signed_demo_cart(scenario: DemoScenario, stateful_part: int = 1) -> CartEvidence:
    key = f"{scenario}_{stateful_part}" if scenario == "stateful" else scenario
    evidence_sufficiency: Literal["sufficient", "ambiguous", "missing"] = "sufficient"
    extra: LineItem | None = None

    if scenario == "valid":
        amount_minor, refundable = 84_000, True
        evidence_text = (
            "This fare is refundable. The cabin is economy. The itinerary is nonstop. "
            "The route is Singapore SIN to Tokyo TYO."
        )
    elif scenario == "budget":
        amount_minor, refundable = 96_000, True
        evidence_text = (
            "This fare is refundable. The cabin is economy. The itinerary is nonstop. "
            "The route is Singapore SIN to Tokyo TYO."
        )
    elif scenario == "semantic":
        amount_minor, refundable = 78_000, False
        evidence_text = (
            "This is a non-refundable fare; refunds are prohibited by the ticket terms. "
            "The cabin is economy. The itinerary is nonstop. The route is Singapore SIN to Tokyo TYO."
        )
    elif scenario == "injected":
        amount_minor, refundable = 85_000, True
        evidence_text = (
            "This fare is refundable. The cabin is economy. The itinerary is nonstop. "
            "The route is Singapore SIN to Tokyo TYO."
        )
        extra = LineItem(
            line_item_id="li_injected_extra",
            description="Unrelated gift card subscription",
            evidence_text="A recurring gift-card subscription is included as a separate cart item.",
            quantity=1,
            amount_minor=1_000,
            attributes={"subscription": True, "product_type": "gift card"},
        )
    elif scenario == "stateful":
        amount_minor, refundable = 50_000, True
        evidence_text = (
            "This fare is refundable. The cabin is economy. The itinerary is nonstop. "
            "The route is Singapore SIN to Tokyo TYO."
        )
    else:
        amount_minor, refundable = 81_000, None
        evidence_text = "Economy nonstop airfare from Singapore SIN to Tokyo TYO."
        evidence_sufficiency = "ambiguous"

    flight_amount = amount_minor - (extra.amount_minor if extra else 0)
    items = [
        _flight_item(
            key,
            flight_amount,
            refundable=refundable,
            evidence_text=evidence_text,
        )
    ]
    if extra:
        items.append(extra)
    unsigned = CartEvidence(
        cart_id=f"cart_{key}_{uuid4().hex[:12]}",
        merchant_id="merchant_air_demo",
        merchant_category="AIRLINE",
        evidence_source="SIMULATED_MERCHANT_SIGNED_CART",
        evidence_trust="trusted",
        evidence_sufficiency=evidence_sufficiency,
        currency="SGD",
        total_amount_minor=amount_minor,
        line_items=items,
        created_at=datetime.now(UTC),
        evidence_reference="unsigned",
    )
    return issue_signed_cart(unsigned)
