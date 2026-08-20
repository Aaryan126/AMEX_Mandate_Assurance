from __future__ import annotations

from typing import Any

from app.feature_contract import (
    CATEGORICAL_FEATURES,
    FEATURE_NAMES,
    FEATURE_PROFILES,
    FEATURE_VERSION,
    FULL_STACK_FEATURES,
    NUMERIC_FEATURES,
    feature_names_for_profile,
    feature_profile_for_names,
    feature_values,
    stack_feature_names_for_profile,
)

__all__ = [
    "CATEGORICAL_FEATURES",
    "FEATURE_NAMES",
    "FEATURE_PROFILES",
    "FEATURE_VERSION",
    "FULL_STACK_FEATURES",
    "NUMERIC_FEATURES",
    "compute_features",
    "feature_names_for_profile",
    "feature_profile_for_names",
    "feature_vector",
    "stack_feature_names_for_profile",
]


def compute_features(row: dict[str, Any]) -> dict[str, float | str]:
    return feature_values(
        budget_minor=int(row["budget_minor"]),
        cart_amount_minor=int(row["cart_amount_minor"]),
        fulfilled_amount_minor=int(row.get("fulfilled_amount_minor", 0)),
        fulfillment_count=int(row.get("fulfillment_count", 0)),
        max_fulfillments=int(row.get("max_fulfillments", 1)),
        line_item_count=int(row.get("line_item_count", 0)),
        missing_evidence_count=int(row.get("missing_evidence_count", 0)),
        semantic_contradiction=float(row.get("semantic_contradiction", 0)),
        semantic_neutral=float(row.get("semantic_neutral", 0)),
        hard_fail_count=int(row.get("hard_fail_count", 0)),
        soft_warning_count=int(row.get("soft_warning_count", 0)),
        mandate_currency=str(row["currency"]),
        cart_currency=str(row["cart_currency"]),
        category_mismatch=bool(row.get("category_mismatch", False)),
        domain=str(row["domain"]),
        merchant_category=str(row.get("cart_category", row["merchant_category"])),
        evidence_sufficiency=str(row["evidence_sufficiency"]),
    )


def feature_vector(
    row: dict[str, Any], feature_names: list[str] | None = None
) -> list[float | str]:
    features = compute_features(row)
    return [features[name] for name in feature_names or FEATURE_NAMES]
