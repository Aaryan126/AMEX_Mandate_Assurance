from __future__ import annotations

import hashlib

from app.commercial_rules import evaluate_commercial_rules

from ml.data.schema import (
    AceDatasetExample,
    DatasetLabels,
    DatasetLineItem,
    DatasetState,
    DeviationLabel,
    EvidenceOrigin,
    ExpectedTreatment,
    Identity,
    SemanticAnnotation,
    SemanticLabel,
)

GENERATOR_VERSION = "grounded-counterfactual-v3"

EXPECTED_COMMERCIAL_FAILURES = {
    "cumulative_overspend": {"CUMULATIVE_BUDGET_EXCEEDED"},
    "near_budget_match": set(),
    "missing_required_evidence": set(),
    "unrelated_add_on": set(),
}


def _child_id(parent: AceDatasetExample, transformation: str) -> str:
    suffix = hashlib.sha256(
        f"{parent.identity.example_id}:{transformation}:{GENERATOR_VERSION}".encode()
    ).hexdigest()[:16]
    return f"ace_cf_{suffix}"


def _base_child(parent: AceDatasetExample, transformation: str) -> AceDatasetExample:
    return parent.model_copy(
        deep=True,
        update={
            "identity": Identity(
                example_id=_child_id(parent, transformation),
                group_id=parent.identity.group_id,
                parent_example_id=parent.identity.example_id,
                sequence_id=parent.identity.sequence_id,
                sequence_position=parent.identity.sequence_position,
            ),
            "provenance": parent.provenance.model_copy(
                update={
                    "evidence_origin": EvidenceOrigin.HYBRID_GROUNDED,
                    "transformation": transformation,
                    "generator_version": GENERATOR_VERSION,
                }
            ),
        },
    )


def validate_counterfactual_invariants(value: AceDatasetExample) -> None:
    transformation = str(value.provenance.transformation)
    if transformation not in EXPECTED_COMMERCIAL_FAILURES:
        raise ValueError(f"unknown counterfactual transformation: {transformation}")
    signals = evaluate_commercial_rules(value.mandate, value.state, value.cart)
    failures = {
        str(signal.reason_code)
        for signal in signals
        if signal.status == "FAIL" and signal.reason_code is not None
    }
    if failures != EXPECTED_COMMERCIAL_FAILURES[transformation]:
        raise ValueError(
            f"{transformation} produced unexpected commercial failures: {sorted(failures)}"
        )
    unattributed_failures = [
        signal.rule_id
        for signal in signals
        if signal.status == "FAIL" and signal.reason_code is None
    ]
    if unattributed_failures:
        raise ValueError(
            f"{transformation} produced unattributed failures: {unattributed_failures}"
        )
    if transformation == "missing_required_evidence" and (
        value.cart.evidence_sufficiency == "sufficient"
    ):
        raise ValueError("missing-evidence counterfactual retained sufficient evidence")
    if transformation == "unrelated_add_on":
        if value.labels.expected_treatment != ExpectedTreatment.STEP_UP:
            raise ValueError("unrelated add-on must follow the semantic STEP_UP contract")
        if "SEMANTIC_UNRELATED_ITEM" not in value.labels.violation_types:
            raise ValueError("unrelated add-on is missing its semantic violation code")


def cumulative_overspend(parent: AceDatasetExample) -> AceDatasetExample:
    budget = next(
        (
            constraint.amount_minor
            for constraint in parent.mandate.constraints
            if constraint.type == "total_budget"
        ),
        None,
    )
    if budget is None or budget <= parent.cart.total_amount_minor:
        raise ValueError(
            "cumulative overspend requires a parent cart below a positive total budget"
        )
    fulfilled = budget - parent.cart.total_amount_minor + max(1, budget // 100)
    child = _base_child(parent, "cumulative_overspend")
    child.provenance.field_origins["state"] = "synthetic_counterfactual"
    fulfillment_count = max(parent.state.fulfillment_count, 1)
    result = child.model_copy(
        update={
            "mandate": child.mandate.model_copy(
                update={
                    "max_fulfillments": max(
                        child.mandate.max_fulfillments, fulfillment_count + 1
                    )
                }
            ),
            "state": DatasetState(
                fulfilled_amount_minor=fulfilled,
                fulfillment_count=fulfillment_count,
                prior_transaction_ids=parent.state.prior_transaction_ids
                or ["prior_grounded_purchase"],
                history_available=True,
            ),
            "labels": DatasetLabels(
                deviation=DeviationLabel.VIOLATION,
                semantic=parent.labels.semantic,
                violation_types=["CUMULATIVE_BUDGET_EXCEEDED"],
                expected_treatment=ExpectedTreatment.HOLD,
                label_source="deterministic_counterfactual",
                reviewer_confidence=1.0,
            ),
        }
    )
    result.provenance.field_origins["mandate.max_fulfillments"] = (
        "synthetic_counterfactual_isolation"
    )
    validate_counterfactual_invariants(result)
    return result


def near_budget_match(parent: AceDatasetExample) -> AceDatasetExample:
    budget = next(
        (
            constraint.amount_minor
            for constraint in parent.mandate.constraints
            if constraint.type == "total_budget"
        ),
        None,
    )
    if budget is None or budget < 1:
        raise ValueError("near-budget match requires a positive total budget")
    child = _base_child(parent, "near_budget_match")
    child.provenance.field_origins["cart.total_amount_minor"] = (
        "synthetic_counterfactual"
    )
    child.provenance.field_origins["cart.line_items.amount_minor"] = (
        "synthetic_counterfactual"
    )
    amount = max(1, budget - 1)
    first, *rest = child.cart.line_items
    remaining = sum(item.amount_minor * item.quantity for item in rest)
    if remaining >= amount:
        raise ValueError(
            "near-budget transformation requires a single dominant line item"
        )
    updated_first = first.model_copy(
        update={"quantity": 1, "amount_minor": amount - remaining}
    )
    result = child.model_copy(
        update={
            "cart": child.cart.model_copy(
                update={
                    "line_items": [updated_first, *rest],
                    "total_amount_minor": amount,
                }
            ),
            "labels": DatasetLabels(
                deviation=DeviationLabel.MATCH,
                semantic=parent.labels.semantic,
                expected_treatment=ExpectedTreatment.APPROVE,
                label_source="deterministic_counterfactual",
                reviewer_confidence=1.0,
            ),
        }
    )
    validate_counterfactual_invariants(result)
    return result


def remove_required_evidence(parent: AceDatasetExample) -> AceDatasetExample:
    child = _base_child(parent, "missing_required_evidence")
    child.provenance.field_origins["cart.evidence_sufficiency"] = (
        "synthetic_counterfactual"
    )
    child.provenance.field_origins["cart.line_items.evidence_text"] = (
        "synthetic_counterfactual_removal"
    )
    line_items = [
        item.model_copy(update={"attributes": {}, "evidence_text": item.description})
        for item in child.cart.line_items
    ]
    result = child.model_copy(
        update={
            "cart": child.cart.model_copy(
                update={"line_items": line_items, "evidence_sufficiency": "ambiguous"}
            ),
            "labels": DatasetLabels(
                deviation=DeviationLabel.AMBIGUOUS,
                semantic=[
                    SemanticAnnotation(
                        constraint_id=constraint.constraint_id,
                        label=SemanticLabel.NEUTRAL,
                        confidence=1.0,
                    )
                    for constraint in parent.mandate.constraints
                    if constraint.type == "semantic_attribute"
                ],
                violation_types=["REQUIRED_ATTRIBUTE_EVIDENCE_MISSING"],
                expected_treatment=ExpectedTreatment.STEP_UP,
                label_source="deterministic_counterfactual",
                reviewer_confidence=1.0,
            ),
        }
    )
    validate_counterfactual_invariants(result)
    return result


def add_unrelated_item(
    parent: AceDatasetExample,
    *,
    product_id: str,
    description: str,
    amount_minor: int,
) -> AceDatasetExample:
    if amount_minor < 0:
        raise ValueError("amount_minor must be non-negative")
    child = _base_child(parent, "unrelated_add_on")
    child.provenance.field_origins["cart.composition"] = "synthetic_counterfactual"
    extra = DatasetLineItem(
        line_item_id=f"li_addon_{product_id}",
        source_product_id=product_id,
        description=description,
        quantity=1,
        amount_minor=amount_minor,
        attributes={},
        evidence_text=description,
    )
    result = child.model_copy(
        update={
            "cart": child.cart.model_copy(
                update={
                    "line_items": [*child.cart.line_items, extra],
                    "total_amount_minor": child.cart.total_amount_minor + amount_minor,
                }
            ),
            "labels": DatasetLabels(
                deviation=DeviationLabel.VIOLATION,
                semantic=parent.labels.semantic,
                violation_types=["SEMANTIC_UNRELATED_ITEM"],
                expected_treatment=ExpectedTreatment.STEP_UP,
                label_source="deterministic_counterfactual",
                reviewer_confidence=1.0,
            ),
        }
    )
    validate_counterfactual_invariants(result)
    return result
