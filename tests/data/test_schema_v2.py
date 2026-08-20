from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.commercial_rules import evaluate_commercial_rules
from pydantic import ValidationError

from ml.data.schema import (
    AceDatasetExample,
    Context,
    DatasetCart,
    DatasetConstraint,
    DatasetLabels,
    DatasetLineItem,
    DatasetMandate,
    DeviationLabel,
    EvidenceOrigin,
    Identity,
    MandateOrigin,
    Provenance,
)
from ml.data.transforms import (
    add_unrelated_item,
    assign_split,
    cumulative_overspend,
    near_budget_match,
    remove_required_evidence,
    validate_counterfactual_invariants,
)


def example() -> AceDatasetExample:
    return AceDatasetExample(
        identity=Identity(example_id="ex_1", group_id="query_1"),
        provenance=Provenance(
            source_dataset="fixture",
            source_version="v1",
            source_record_id="row_1",
            source_url="https://example.test/data",
            source_license="CC-BY-4.0",
            evidence_origin=EvidenceOrigin.REAL_PUBLIC,
            mandate_origin=MandateOrigin.SOURCE_QUERY,
            acquired_at=datetime(2026, 8, 17, tzinfo=UTC),
            field_origins={
                "cart.line_items": "real_public",
                "cart.total_amount_minor": "synthetic",
            },
        ),
        context=Context(domain="retail", locale="en-US", market="US"),
        mandate=DatasetMandate(
            objective_text="Purchase a waterproof laptop backpack under USD 100.",
            constraints=[
                DatasetConstraint(
                    constraint_id="budget",
                    type="total_budget",
                    operator="lte",
                    amount_minor=10000,
                    currency="USD",
                    currency_exponent=2,
                ),
                DatasetConstraint(
                    constraint_id="waterproof",
                    type="semantic_attribute",
                    operator="required",
                    value="waterproof",
                ),
            ],
        ),
        cart=DatasetCart(
            cart_id="cart_1",
            merchant_id="merchant_fixture",
            merchant_category="BAGS",
            evidence_source="PUBLIC_DATASET",
            evidence_trust="trusted",
            evidence_sufficiency="sufficient",
            currency="USD",
            currency_exponent=2,
            total_amount_minor=8000,
            line_items=[
                DatasetLineItem(
                    line_item_id="li_1",
                    source_product_id="p1",
                    description="Waterproof laptop backpack",
                    quantity=1,
                    amount_minor=8000,
                    attributes={"waterproof": True},
                    evidence_text="Waterproof laptop backpack",
                )
            ],
        ),
        labels=DatasetLabels(
            deviation=DeviationLabel.MATCH,
            expected_treatment="APPROVE",
            label_source="weak_esci_mapping",
        ),
    )


def test_schema_round_trip_and_forbids_unknown_fields() -> None:
    value = example()
    assert AceDatasetExample.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        AceDatasetExample.model_validate(
            {**value.model_dump(), "attack_family": "leak"}
        )


def test_cart_total_must_match_items() -> None:
    value = example().model_dump()
    value["cart"]["total_amount_minor"] = 7999
    with pytest.raises(ValidationError, match="cart total"):
        AceDatasetExample.model_validate(value)


def test_grounded_counterfactuals_preserve_group_and_parent() -> None:
    parent = assign_split(example())
    variants = [
        cumulative_overspend(parent),
        near_budget_match(parent),
        remove_required_evidence(parent),
        add_unrelated_item(
            parent, product_id="gift", description="Gift card", amount_minor=500
        ),
    ]
    assert {variant.identity.group_id for variant in variants} == {
        parent.identity.group_id
    }
    assert {variant.split.name for variant in variants} == {parent.split.name}
    assert all(
        variant.identity.parent_example_id == parent.identity.example_id
        for variant in variants
    )
    assert all(
        variant.provenance.evidence_origin == "hybrid_grounded" for variant in variants
    )
    assert (
        variants[0].state.fulfilled_amount_minor + variants[0].cart.total_amount_minor
        > 10000
    )
    assert variants[1].cart.total_amount_minor == 9999
    assert variants[2].labels.deviation == DeviationLabel.AMBIGUOUS
    assert variants[3].cart.total_amount_minor == 8500
    assert variants[3].labels.expected_treatment == "STEP_UP"
    assert variants[3].labels.violation_types == ["SEMANTIC_UNRELATED_ITEM"]
    for variant in variants:
        validate_counterfactual_invariants(variant)


def test_counterfactuals_have_exact_intended_rule_triggers() -> None:
    parent = assign_split(example())
    variants = {
        "cumulative_overspend": cumulative_overspend(parent),
        "near_budget_match": near_budget_match(parent),
        "missing_required_evidence": remove_required_evidence(parent),
        "unrelated_add_on": add_unrelated_item(
            parent, product_id="gift", description="Gift card", amount_minor=500
        ),
    }
    expected = {
        "cumulative_overspend": {"CUMULATIVE_BUDGET_EXCEEDED"},
        "near_budget_match": set(),
        "missing_required_evidence": set(),
        "unrelated_add_on": set(),
    }
    for name, value in variants.items():
        failures = {
            signal.reason_code
            for signal in evaluate_commercial_rules(
                value.mandate, value.state, value.cart
            )
            if signal.status == "FAIL" and signal.reason_code
        }
        assert failures == expected[name]


def test_unrelated_add_on_rejects_accidental_budget_breach() -> None:
    with pytest.raises(ValueError, match="unexpected commercial failures"):
        add_unrelated_item(
            example(), product_id="expensive", description="Gift card", amount_minor=3000
        )


def test_split_is_deterministic_and_grouped() -> None:
    first = assign_split(example())
    second = assign_split(example())
    assert first.split == second.split
    child = add_unrelated_item(
        first, product_id="p2", description="Accessory", amount_minor=100
    )
    assert child.split.name == first.split.name
