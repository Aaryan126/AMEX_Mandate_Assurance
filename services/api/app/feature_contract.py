from __future__ import annotations

FEATURE_VERSION = "features-v2"
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


def feature_values(
    *,
    budget_minor: int,
    cart_amount_minor: int,
    fulfilled_amount_minor: int,
    fulfillment_count: int,
    max_fulfillments: int,
    line_item_count: int,
    missing_evidence_count: int,
    semantic_contradiction: float,
    semantic_neutral: float,
    hard_fail_count: int,
    soft_warning_count: int,
    mandate_currency: str,
    cart_currency: str,
    category_mismatch: bool,
    domain: str,
    merchant_category: str,
    evidence_sufficiency: str,
) -> dict[str, float | str]:
    """The versioned, pure feature contract shared by training and serving."""
    budget = max(budget_minor, 1)
    values: dict[str, float | str] = {
        "amount_ratio": cart_amount_minor / budget,
        "amount_delta_ratio": (cart_amount_minor - budget) / budget,
        "cumulative_utilization": (fulfilled_amount_minor + cart_amount_minor) / budget,
        "fulfillment_utilization": (fulfillment_count + 1) / max(max_fulfillments, 1),
        "line_item_count": float(line_item_count),
        "missing_evidence_count": float(missing_evidence_count),
        "semantic_contradiction": float(semantic_contradiction),
        "semantic_neutral": float(semantic_neutral),
        "hard_fail_count": float(hard_fail_count),
        "soft_warning_count": float(soft_warning_count),
        "currency_mismatch": float(mandate_currency != cart_currency),
        "category_mismatch": float(category_mismatch),
        "domain": domain,
        "merchant_category": merchant_category,
        "evidence_sufficiency": evidence_sufficiency,
    }
    assert list(values) == FEATURE_NAMES
    return values
