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

FEATURE_PROFILES = {
    "full-v2": FEATURE_NAMES,
    "shortcut-safe-v2": [name for name in FEATURE_NAMES if name != "line_item_count"],
    "no-semantic-v2": [
        name
        for name in FEATURE_NAMES
        if name not in {"semantic_contradiction", "semantic_neutral"}
    ],
    "shortcut-safe-no-semantic-v2": [
        name
        for name in FEATURE_NAMES
        if name
        not in {"line_item_count", "semantic_contradiction", "semantic_neutral"}
    ],
}
FULL_STACK_FEATURES = [
    "semantic_contradiction",
    "semantic_neutral",
    "catboost_probability",
    "hard_fail_count",
    "soft_warning_count",
]


def feature_names_for_profile(profile: str) -> list[str]:
    try:
        return list(FEATURE_PROFILES[profile])
    except KeyError as exc:
        raise ValueError(f"unknown feature profile: {profile}") from exc


def feature_profile_for_names(names: list[str]) -> str:
    matches = [profile for profile, values in FEATURE_PROFILES.items() if names == values]
    if len(matches) != 1:
        raise ValueError("model feature names do not match a declared feature profile")
    return matches[0]


def stack_feature_names_for_profile(profile: str) -> list[str]:
    selected = feature_names_for_profile(profile)
    return [
        name
        for name in FULL_STACK_FEATURES
        if name not in {"semantic_contradiction", "semantic_neutral"}
        or name in selected
    ]


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
