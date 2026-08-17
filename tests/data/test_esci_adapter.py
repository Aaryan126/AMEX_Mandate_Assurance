from __future__ import annotations

import json
from pathlib import Path

from ml.data.acquire_esci import source_url
from ml.data.adapters.esci import EsciAdapter
from ml.data.schema import DeviationLabel

FIXTURE = Path("ml/data/fixtures/esci_joined.jsonl")
REVISION = "a" * 40


def records() -> list[dict]:
    return [
        json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()
    ]


def test_esci_normalizes_english_with_field_level_provenance() -> None:
    example = next(iter(EsciAdapter(revision=REVISION).normalize(records()[0])))
    assert example.context.locale == "en-US"
    assert example.cart.currency == "USD"
    assert example.cart.currency_exponent == 2
    assert example.labels.deviation == DeviationLabel.MATCH
    assert example.provenance.field_origins["cart.total_amount_minor"] == "synthetic"
    assert example.identity.group_id == "esci_query_q1"


def test_esci_normalizes_japanese_and_preserves_zero_decimal_currency() -> None:
    example = next(iter(EsciAdapter(revision=REVISION).normalize(records()[1])))
    assert example.context.locale == "ja-JP"
    assert example.cart.currency == "JPY"
    assert example.cart.currency_exponent == 0
    assert example.labels.deviation == DeviationLabel.AMBIGUOUS
    assert "撥水" in example.cart.line_items[0].evidence_text


def test_esci_rejects_mutable_revision() -> None:
    try:
        EsciAdapter(revision="main")
    except ValueError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("mutable revisions must be rejected")


def test_acquisition_uses_git_lfs_media_endpoint() -> None:
    url = source_url("a" * 40, "shopping_queries_dataset_examples.parquet")
    assert url.startswith("https://media.githubusercontent.com/media/")
