from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from .schemas import CartEvidence, Mandate, MandateState, RuleResult, RuleStatus, SemanticResult

FEATURE_VERSION = "features-v1"
FEATURE_NAMES = [
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
    "domain",
    "merchant_category",
    "evidence_sufficiency",
]


class StructuredScorer(Protocol):
    version: str | None

    def score(
        self,
        mandate: Mandate,
        state: MandateState,
        cart: CartEvidence,
        rules: list[RuleResult],
        semantics: list[SemanticResult],
    ) -> float: ...


def runtime_features(
    mandate: Mandate,
    state: MandateState,
    cart: CartEvidence,
    rules: list[RuleResult],
    semantics: list[SemanticResult],
) -> dict[str, float | str]:
    budget_constraint = next(
        (constraint for constraint in mandate.constraints if constraint.type.value == "total_budget"), None
    )
    budget = max(budget_constraint.amount_minor if budget_constraint else cart.total_amount_minor, 1)
    hard_fail_count = sum(result.status == RuleStatus.FAIL for result in rules)
    soft_warning_count = sum(
        result.status in {RuleStatus.WARN, RuleStatus.NOT_EVALUABLE} for result in rules
    )
    categories = {"AIRLINE": "travel", "HOTEL": "travel", "RESTAURANT": "dining"}
    missing = sum(result.status == RuleStatus.NOT_EVALUABLE for result in rules)
    features: dict[str, float | str] = {
        "amount_ratio": cart.total_amount_minor / budget,
        "amount_delta_ratio": (cart.total_amount_minor - budget) / budget,
        "cumulative_utilization": (state.fulfilled_amount_minor + cart.total_amount_minor) / budget,
        "fulfillment_utilization": (state.fulfillment_count + 1) / max(mandate.max_fulfillments, 1),
        "line_item_count": float(len(cart.line_items)),
        "missing_evidence_count": float(missing),
        "semantic_contradiction": max((value.contradiction for value in semantics), default=0.0),
        "semantic_neutral": max((value.neutral for value in semantics), default=0.0),
        "hard_fail_count": float(hard_fail_count),
        "soft_warning_count": float(soft_warning_count),
        "currency_mismatch": float(bool(budget_constraint and cart.currency != budget_constraint.currency)),
        "category_mismatch": 0.0,
        "domain": categories.get(cart.merchant_category, "retail"),
        "merchant_category": cart.merchant_category,
        "evidence_sufficiency": "ambiguous" if missing else "sufficient",
    }
    assert list(features) == FEATURE_NAMES
    return features


class HeuristicStructuredScorer:
    version = None

    def score(
        self,
        mandate: Mandate,
        state: MandateState,
        cart: CartEvidence,
        rules: list[RuleResult],
        semantics: list[SemanticResult],
    ) -> float:
        features = runtime_features(mandate, state, cart, rules, semantics)
        raw = (
            0.04
            + 0.35 * min(float(features["hard_fail_count"]), 2)
            + 0.45 * float(features["semantic_contradiction"])
            + 0.18 * float(features["semantic_neutral"])
        )
        return min(raw, 0.99)


class CatBoostArtifactScorer:
    def __init__(self, artifact_path: Path, manifest_path: Path) -> None:
        from catboost import CatBoostClassifier

        manifest = json.loads(manifest_path.read_text())
        if manifest["feature_names"] != FEATURE_NAMES or manifest["feature_version"] != FEATURE_VERSION:
            raise RuntimeError("CatBoost artifact feature schema is incompatible with this API build")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if checksum != manifest["artifact_sha256"]:
            raise RuntimeError("CatBoost artifact checksum does not match its manifest")
        self.model = CatBoostClassifier()
        self.model.load_model(artifact_path)
        self.version = str(manifest["model_version"])

    def score(
        self,
        mandate: Mandate,
        state: MandateState,
        cart: CartEvidence,
        rules: list[RuleResult],
        semantics: list[SemanticResult],
    ) -> float:
        features = runtime_features(mandate, state, cart, rules, semantics)
        vector = [[features[name] for name in FEATURE_NAMES]]
        return float(self.model.predict_proba(vector)[0][1])


def configured_structured_scorer() -> StructuredScorer:
    artifact = Path(os.getenv("ACE_CATBOOST_ARTIFACT", "artifacts/models/catboost-v1.cbm"))
    manifest = Path(
        os.getenv("ACE_CATBOOST_MANIFEST", "artifacts/models/catboost-v1.manifest.json")
    )
    if os.getenv("ACE_MODEL_MODE") == "artifact" and artifact.exists() and manifest.exists():
        return CatBoostArtifactScorer(artifact, manifest)
    return HeuristicStructuredScorer()

