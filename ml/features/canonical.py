from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.commercial_rules import evaluate_commercial_rules

from ml.data.schema import AceDatasetExample, DeviationLabel


def load_semantic_predictions(path: Path) -> dict[str, tuple[float, float]]:
    predictions: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with path.open() as source:
        for line in source:
            if not line.strip():
                continue
            value = json.loads(line)
            predictions[value["example_id"]].append(
                (float(value["contradiction"]), float(value["neutral"]))
            )
    return {
        example_id: (
            max(value[0] for value in values),
            max(value[1] for value in values),
        )
        for example_id, values in predictions.items()
    }


def canonical_feature_row(
    example: AceDatasetExample,
    semantic_prediction: tuple[float, float],
) -> dict[str, Any]:
    budget_constraint = next(
        (
            value
            for value in example.mandate.constraints
            if value.type == "total_budget"
        ),
        None,
    )
    budget = (
        budget_constraint.amount_minor
        if budget_constraint and budget_constraint.amount_minor is not None
        else example.cart.total_amount_minor
    )
    mandate_currency = (
        budget_constraint.currency
        if budget_constraint and budget_constraint.currency
        else example.cart.currency
    )
    rule_signals = evaluate_commercial_rules(
        example.mandate, example.state, example.cart
    )
    hard_fail_count = sum(signal.status == "FAIL" for signal in rule_signals)
    critical_hold_count = sum(
        signal.status == "FAIL" and signal.severity == "critical"
        for signal in rule_signals
    )
    prohibited_categories: set[str] = set()
    for constraint in example.mandate.constraints:
        if constraint.type == "prohibited_category":
            values = (
                constraint.value
                if isinstance(constraint.value, list)
                else [constraint.value]
            )
            prohibited_categories.update(
                str(value).upper() for value in values if value is not None
            )
    category_mismatch = example.cart.merchant_category.upper() in prohibited_categories

    missing = int(example.cart.evidence_sufficiency != "sufficient")
    contradiction, neutral = semantic_prediction
    label = {
        DeviationLabel.MATCH: 0,
        DeviationLabel.VIOLATION: 1,
        DeviationLabel.AMBIGUOUS: None,
        None: None,
    }[example.labels.deviation]
    return {
        "dataset_version": "ace-canonical-features-v2",
        "example_id": example.identity.example_id,
        "seed_id": example.identity.group_id,
        "parent_example_id": example.identity.parent_example_id,
        "split": example.split.name,
        "dataset": example.provenance.source_dataset,
        "locale": example.context.locale,
        "domain": example.context.domain,
        "budget_minor": budget,
        "cart_amount_minor": example.cart.total_amount_minor,
        "fulfilled_amount_minor": example.state.fulfilled_amount_minor,
        "fulfillment_count": example.state.fulfillment_count,
        "max_fulfillments": example.mandate.max_fulfillments,
        "line_item_count": len(example.cart.line_items),
        "missing_evidence_count": missing,
        "semantic_contradiction": contradiction,
        "semantic_neutral": neutral,
        "hard_fail_count": hard_fail_count,
        "critical_hold_count": critical_hold_count,
        "soft_warning_count": missing,
        "currency": mandate_currency,
        "cart_currency": example.cart.currency,
        "category_mismatch": category_mismatch,
        "merchant_category": example.cart.merchant_category,
        "cart_category": example.cart.merchant_category,
        "evidence_sufficiency": example.cart.evidence_sufficiency,
        "label": label,
        "expected_treatment": example.labels.expected_treatment,
        "attack_family": example.provenance.transformation,
        "label_source": example.labels.label_source,
    }
