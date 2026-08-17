from __future__ import annotations

from typing import Any

FEATURE_VERSION = "features-v1"
NUMERIC_FEATURES = [
    "amount_ratio",
    "amount_delta_ratio",
    "cumulative_utilization",
    "fulfillment_utilization",
    "line_item_count",
    "missing_evidence_count",
    "semantic_contradiction",
    "semantic_neutral",
    "hard_fail_count",
    "soft_warning_count",
    "currency_mismatch",
    "category_mismatch",
]
CATEGORICAL_FEATURES = ["domain", "merchant_category", "evidence_sufficiency"]
FEATURE_NAMES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def compute_features(row: dict[str, Any]) -> dict[str, float | str]:
    budget = max(int(row["budget_minor"]), 1)
    amount = int(row["cart_amount_minor"])
    cumulative = int(row.get("fulfilled_amount_minor", 0)) + amount
    max_fulfillments = max(int(row.get("max_fulfillments", 1)), 1)
    features: dict[str, float | str] = {
        "amount_ratio": amount / budget,
        "amount_delta_ratio": (amount - budget) / budget,
        "cumulative_utilization": cumulative / budget,
        "fulfillment_utilization": (int(row.get("fulfillment_count", 0)) + 1) / max_fulfillments,
        "line_item_count": float(row.get("line_item_count", 0)),
        "missing_evidence_count": float(row.get("missing_evidence_count", 0)),
        "semantic_contradiction": float(row.get("semantic_contradiction", 0)),
        "semantic_neutral": float(row.get("semantic_neutral", 0)),
        "hard_fail_count": float(row.get("hard_fail_count", 0)),
        "soft_warning_count": float(row.get("soft_warning_count", 0)),
        "currency_mismatch": float(row["currency"] != row["cart_currency"]),
        "category_mismatch": float(row["merchant_category"] != row["cart_category"]),
        "domain": str(row["domain"]),
        "merchant_category": str(row["merchant_category"]),
        "evidence_sufficiency": str(row["evidence_sufficiency"]),
    }
    assert list(features) == FEATURE_NAMES
    return features


def feature_vector(row: dict[str, Any]) -> list[float | str]:
    features = compute_features(row)
    return [features[name] for name in FEATURE_NAMES]

