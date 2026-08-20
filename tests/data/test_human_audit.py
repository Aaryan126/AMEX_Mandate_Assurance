from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.annotations import AnnotationDecision, AnnotationReview, AnnotationStore

from ml.data.human_audit import (
    audit_status,
    build_audit_report,
    prepare_assisted_inputs,
    prepare_audit,
    validate_prepared_audit,
)
from ml.data.schema import AceDatasetExample


def _example(
    index: int,
    *,
    label_source: str,
    transformation: str = "none",
    fulfilled: int = 0,
) -> AceDatasetExample:
    treatment = "HOLD" if fulfilled else "APPROVE"
    deviation = "VIOLATION" if fulfilled else "MATCH"
    return AceDatasetExample.model_validate(
        {
            "identity": {
                "example_id": f"audit-{index}",
                "group_id": f"group-{index}",
                "parent_example_id": f"parent-{index}" if transformation != "none" else None,
            },
            "provenance": {
                "source_dataset": "fixture",
                "source_version": "v1",
                "source_record_id": str(index),
                "source_url": "https://example.test",
                "source_license": "CC0",
                "evidence_origin": (
                    "hybrid_grounded" if transformation != "none" else "real_public"
                ),
                "mandate_origin": "source_query",
                "transformation": transformation,
                "generator_version": "fixture-v1" if transformation != "none" else None,
                "field_origins": {"secret": "synthetic"},
            },
            "context": {"domain": "retail", "locale": "en-US", "market": "US"},
            "mandate": {
                "objective_text": "Buy a waterproof backpack under USD 100",
                "constraints": [
                    {
                        "constraint_id": "budget",
                        "type": "total_budget",
                        "operator": "lte",
                        "amount_minor": 10000,
                        "currency": "USD",
                        "currency_exponent": 2,
                    },
                    {
                        "constraint_id": "attribute",
                        "type": "semantic_attribute",
                        "operator": "required",
                        "value": "waterproof",
                    },
                ],
                "max_fulfillments": 2,
            },
            "cart": {
                "cart_id": f"cart-{index}",
                "merchant_id": "merchant",
                "merchant_category": "BAGS",
                "evidence_source": "fixture",
                "evidence_trust": "trusted",
                "evidence_sufficiency": "sufficient",
                "currency": "USD",
                "currency_exponent": 2,
                "total_amount_minor": 8000,
                "line_items": [
                    {
                        "line_item_id": f"item-{index}",
                        "description": "Waterproof backpack",
                        "quantity": 1,
                        "amount_minor": 8000,
                        "attributes": {"waterproof": True},
                        "evidence_text": "Waterproof backpack",
                    }
                ],
            },
            "state": {
                "fulfilled_amount_minor": fulfilled,
                "fulfillment_count": 1 if fulfilled else 0,
                "history_available": True,
            },
            "labels": {
                "deviation": deviation,
                "semantic": [
                    {
                        "constraint_id": "attribute",
                        "label": "ENTAILMENT",
                        "confidence": 1.0,
                    }
                ],
                "violation_types": ["CUMULATIVE_BUDGET_EXCEEDED"] if fulfilled else [],
                "expected_treatment": treatment,
                "label_source": label_source,
                "reviewer_confidence": 1.0,
            },
            "split": {"name": "golden", "grouping_keys": [f"group-{index}"]},
        }
    )


def _write(path: Path, values: list[AceDatasetExample]) -> None:
    path.write_text("".join(value.model_dump_json() + "\n" for value in values))


def _prepare(tmp_path: Path) -> Path:
    development = tmp_path / "development.jsonl"
    holdout = tmp_path / "holdout.jsonl"
    _write(
        development,
        [
            _example(1, label_source="weak_esci_mapping"),
            _example(
                2,
                label_source="deterministic_counterfactual",
                transformation="cumulative_overspend",
                fulfilled=3000,
            ),
            _example(3, label_source="llm_consensus"),
        ],
    )
    _write(
        holdout,
        [
            _example(4, label_source="llm_consensus"),
            _example(5, label_source="llm_adjudicated"),
            _example(6, label_source="llm_adjudicated"),
        ],
    )
    output = tmp_path / "audit"
    prepare_audit(development, holdout, output, rows=6)
    return output


def _review(reviewer: str, treatment: str) -> AnnotationReview:
    return AnnotationReview(
        reviewer_id=reviewer,
        deviation="VIOLATION" if treatment == "HOLD" else "MATCH",
        semantic_label="ENTAILMENT",
        expected_treatment=treatment,
        violation_types=["CUMULATIVE_BUDGET_EXCEEDED"] if treatment == "HOLD" else [],
        confidence=0.9,
    )


def test_prepare_audit_is_bound_stratified_and_blinded(tmp_path: Path) -> None:
    output = _prepare(tmp_path)
    assert validate_prepared_audit(output) == {"status": "valid", "rows": 6}
    queue = [json.loads(line) for line in (output / "review-queue.jsonl").read_text().splitlines()]
    assert len({row["identity"]["group_id"] for row in queue}) == 6
    assert all(row["labels"]["label_source"] == "unreviewed" for row in queue)
    assert all(row["provenance"]["transformation"] == "none" for row in queue)
    assert all("audit_context" in row for row in queue)
    assert audit_status(output)["unreviewed"] == 6
    assisted = prepare_assisted_inputs(output)
    assert assisted["rows"] == 6
    assert assisted["provenance"] == "llm_assisted_not_human"
    assert len(
        (output / "assisted/assisted-review-dataset.jsonl").read_text().splitlines()
    ) == 6


def test_report_requires_real_human_ids_and_resolved_reviews(tmp_path: Path) -> None:
    output = _prepare(tmp_path)
    store = AnnotationStore(output / "review-queue.jsonl", output / "human-reviews.sqlite3")
    store.initialize()
    ledger = {
        row["example_id"]: row
        for row in (
            json.loads(line) for line in (output / "audit-ledger.jsonl").read_text().splitlines()
        )
    }
    ids = sorted(ledger)
    for example_id in ids:
        treatment = ledger[example_id]["oracle"]["deterministic_treatment"]
        store.submit_review(example_id, _review("human-a", treatment))
        second_treatment = "STEP_UP" if example_id == ids[0] else treatment
        store.submit_review(example_id, _review("human-b", second_treatment))
    store.adjudicate(
        ids[0],
        AnnotationDecision(
            reviewer_id="human-c",
            adjudicator_id="human-c",
            deviation="MATCH",
            semantic_label="ENTAILMENT",
            expected_treatment=ledger[ids[0]]["oracle"]["deterministic_treatment"],
            confidence=0.9,
        ),
    )
    report = build_audit_report(output, tmp_path / "report.json")
    assert report["complete"] is True
    assert report["rows"] == 6
    assert report["disagreements_adjudicated"] == 1
    assert report["deterministic_oracle_agreement"] == 1.0


def test_report_refuses_incomplete_audit(tmp_path: Path) -> None:
    output = _prepare(tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        build_audit_report(output, tmp_path / "report.json")
