from __future__ import annotations

import pytest

from ml.data.adapters.base import AdapterError
from ml.data.adapters.option2 import (
    AmazonM2Adapter,
    Db1bAdapter,
    OnlineRetailAdapter,
    UsaSpendingAdapter,
)
from ml.data.schema import AceDatasetExample


@pytest.mark.parametrize(
    ("adapter", "record", "dataset", "domain"),
    [
        (
            AmazonM2Adapter("revision-2026"),
            {
                "session_id": "session-1",
                "previous_product_ids": ["p0"],
                "previous_titles": ["Black laptop sleeve"],
                "next_product_id": "p1",
                "next_title": "Black 15 inch laptop bag",
                "locale": "UK",
                "next_price": 45.5,
                "currency": "GBP",
            },
            "amazon-m2",
            "retail",
        ),
        (
            OnlineRetailAdapter("2009-2011"),
            {
                "invoice": "i1",
                "stock_code": "s1",
                "description": "CERAMIC MUG",
                "quantity": 2,
                "unit_price": 4.25,
                "country": "United Kingdom",
            },
            "uci-online-retail-ii",
            "retail",
        ),
        (
            Db1bAdapter("2025-Q1"),
            {
                "itinerary_id": "it1",
                "origin": "SIN",
                "destination": "SFO",
                "market_fare": 550,
                "carrier": "XX",
            },
            "bts-db1b",
            "travel",
        ),
        (
            UsaSpendingAdapter("2026-08"),
            {
                "award_id": "a1",
                "recipient": "Supplier A",
                "description": "Cloud infrastructure services",
                "amount": 10000,
            },
            "usaspending-awards",
            "procurement",
        ),
    ],
)
def test_option2_adapters_emit_the_same_canonical_contract(
    adapter, record: dict, dataset: str, domain: str
) -> None:
    value = next(iter(adapter.normalize(record)))
    assert AceDatasetExample.model_validate(value.model_dump()) == value
    assert value.provenance.source_dataset == dataset
    assert value.provenance.evidence_origin == "real_public"
    assert value.context.domain == domain
    assert value.cart.total_amount_minor == sum(
        item.amount_minor * item.quantity for item in value.cart.line_items
    )
    assert any(
        constraint.type == "total_budget" for constraint in value.mandate.constraints
    )
    if dataset == "amazon-m2":
        assert value.labels.label_source == "weak_session_transition"
        assert value.context.locale == "en-GB"


def test_option2_adapter_rejects_source_lock_mismatch(tmp_path) -> None:
    (tmp_path / "records.jsonl").write_text("{}\n")
    adapter = AmazonM2Adapter("fixture", sha256="0" * 64)
    with pytest.raises(AdapterError, match="checksum"):
        adapter.validate_source(tmp_path)
