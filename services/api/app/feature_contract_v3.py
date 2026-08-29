from __future__ import annotations

import math

from .feature_contract import CATEGORICAL_FEATURES
from .feature_contract import NUMERIC_FEATURES as V2_NUMERIC_FEATURES

FEATURE_VERSION = "features-v3"
SEMANTIC_DERIVED_FEATURES = [
    "semantic_entailment",
    "semantic_risk",
    "semantic_entropy",
    "semantic_top2_margin",
    "semantic_contradiction_entailment_margin",
]
NUMERIC_FEATURES = [*V2_NUMERIC_FEATURES, *SEMANTIC_DERIVED_FEATURES]
FEATURE_NAMES = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]
FEATURE_PROFILES = {
    "full-v3": FEATURE_NAMES,
    "shortcut-safe-v3": [name for name in FEATURE_NAMES if name != "line_item_count"],
    "no-semantic-v3": [
        name for name in FEATURE_NAMES if not name.startswith("semantic_")
    ],
}


def semantic_derived_values(
    *, contradiction: float, neutral: float, entailment: float
) -> dict[str, float]:
    probabilities = [float(contradiction), float(neutral), float(entailment)]
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in probabilities):
        raise ValueError("semantic probabilities must be finite and in [0, 1]")
    total = sum(probabilities)
    if not math.isclose(total, 1.0, rel_tol=0, abs_tol=1e-5):
        raise ValueError("semantic probabilities must sum to one")
    ordered = sorted(probabilities, reverse=True)
    entropy = -sum(value * math.log(value) for value in probabilities if value > 0)
    return {
        "semantic_entailment": probabilities[2],
        "semantic_risk": max(probabilities[0], probabilities[1]),
        "semantic_entropy": entropy / math.log(3),
        "semantic_top2_margin": ordered[0] - ordered[1],
        "semantic_contradiction_entailment_margin": probabilities[0]
        - probabilities[2],
    }


def feature_names_for_profile(profile: str) -> list[str]:
    try:
        return list(FEATURE_PROFILES[profile])
    except KeyError as exc:
        raise ValueError(f"unknown features-v3 profile: {profile}") from exc
