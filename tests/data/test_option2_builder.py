from __future__ import annotations

from collections import Counter

from ml.data.adapters.option2 import (
    AmazonM2Adapter,
    Db1bAdapter,
    OnlineRetailAdapter,
    UsaSpendingAdapter,
)
from ml.data.build_option2 import construct_option2


def _source_values() -> dict[str, list]:
    adapters = {
        "amazon-m2": AmazonM2Adapter("fixture"),
        "uci-online-retail-ii": OnlineRetailAdapter("fixture"),
        "bts-db1b": Db1bAdapter("fixture"),
        "usaspending-awards": UsaSpendingAdapter("fixture"),
    }
    output = {name: [] for name in adapters}
    for index in range(50):
        records = {
            "amazon-m2": {
                "session_id": f"session-{index}",
                "previous_product_ids": [f"previous-{index}"],
                "previous_titles": [f"Previous product {index}"],
                "next_product_id": f"p{index}",
                "next_title": f"Product {index}",
                "locale": "UK",
            },
            "uci-online-retail-ii": {
                "invoice": f"i{index}",
                "stock_code": f"s{index}",
                "description": f"Retail item {index}",
                "quantity": 2,
                "unit_price": 5,
            },
            "bts-db1b": {
                "itinerary_id": f"it{index}",
                "origin": "SFO",
                "destination": "JFK",
                "market_fare": 300 + index,
            },
            "usaspending-awards": {
                "award_id": f"a{index}",
                "recipient": f"Supplier {index}",
                "description": f"Procurement {index}",
                "amount": 1000 + index,
            },
        }
        for name, adapter in adapters.items():
            output[name].extend(adapter.normalize(records[name]))
    return output


def test_option2_builder_produces_exact_public_synthetic_and_split_mix() -> None:
    first = construct_option2(_source_values(), size=100, review_count=4)
    second = construct_option2(_source_values(), size=100, review_count=4)
    assert [value.model_dump_json() for value in first] == [
        value.model_dump_json() for value in second
    ]
    assert len(first) == 100
    assert sum(value.provenance.transformation == "none" for value in first) == 70
    assert sum(value.provenance.transformation != "none" for value in first) == 30
    assert sum(value.labels.label_source == "unreviewed" for value in first) == 4
    assert Counter(value.split.name for value in first) == {
        "train": 70,
        "validation": 10,
        "calibration": 10,
        "golden": 10,
    }
    by_id = {value.identity.example_id: value for value in first}
    for value in first:
        if value.identity.parent_example_id in by_id:
            assert (
                value.split.name == by_id[value.identity.parent_example_id].split.name
            )
