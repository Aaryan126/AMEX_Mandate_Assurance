from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas import CartEvidence, LineItem

OBJECTIVE = (
    "Book a refundable economy flight from Singapore to Tokyo, departing 7 September "
    "and returning 10 September, nonstop if available, total fare under S$900. "
    "Do not purchase add-ons."
)


def cart(
    *,
    amount_minor: int = 84000,
    refundable: bool | None = True,
    extra_item: str | None = None,
    cart_id: str | None = None,
) -> CartEvidence:
    attributes = {
        "cabin": "economy",
        "stops": 0,
        "origin": "SIN",
        "destination": "TYO",
        "outbound_date": "2026-09-07",
        "return_date": "2026-09-10",
    }
    if refundable is not None:
        attributes["refundable"] = refundable
    refundability_label = (
        "Refundable" if refundable is True else "Non-refundable" if refundable is False else "Return"
    )
    items = [
        LineItem(
            line_item_id="li_flight",
            description=refundability_label + " economy airfare SIN to TYO",
            quantity=1,
            amount_minor=amount_minor - (1000 if extra_item else 0),
            attributes=attributes,
        )
    ]
    if extra_item:
        items.append(
            LineItem(
                line_item_id="li_extra",
                description=extra_item,
                quantity=1,
                amount_minor=1000,
            )
        )
    return CartEvidence(
        cart_id=cart_id or f"cart_{uuid4().hex[:8]}",
        merchant_id="merchant_air_demo",
        merchant_category="AIRLINE",
        evidence_source="SIMULATED_MERCHANT_SIGNED_CART",
        evidence_trust="trusted",
        currency="SGD",
        total_amount_minor=amount_minor,
        line_items=items,
        created_at=datetime.now(UTC),
        evidence_reference=f"evidence_{uuid4().hex[:8]}",
    )
