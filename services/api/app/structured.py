from __future__ import annotations

import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from .feature_contract import FEATURE_NAMES, FEATURE_VERSION, feature_values
from .schemas import CartEvidence, Mandate, MandateState, RuleResult, RuleStatus, SemanticResult


class StructuredScorer(Protocol):
    version: str | None
    catboost_version: str | None
    stacker_version: str | None
    calibrator_version: str | None
    step_up_threshold: float | None
    semantic_model_versions: list[str] | None

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
    budget = budget_constraint.amount_minor if budget_constraint else cart.total_amount_minor
    hard_fail_count = sum(result.status == RuleStatus.FAIL for result in rules)
    soft_warning_count = sum(result.status in {RuleStatus.WARN, RuleStatus.NOT_EVALUABLE} for result in rules)
    categories = {"AIRLINE": "travel", "HOTEL": "travel", "RESTAURANT": "dining"}
    missing = sum(result.status == RuleStatus.NOT_EVALUABLE for result in rules)
    prohibited_categories = {
        str(value).upper()
        for constraint in mandate.constraints
        if constraint.type.value == "prohibited_category"
        for value in (constraint.value if isinstance(constraint.value, list) else [constraint.value])
        if value is not None
    }
    return feature_values(
        budget_minor=budget,
        cart_amount_minor=cart.total_amount_minor,
        fulfilled_amount_minor=state.fulfilled_amount_minor,
        fulfillment_count=state.fulfillment_count,
        max_fulfillments=mandate.max_fulfillments,
        line_item_count=len(cart.line_items),
        missing_evidence_count=missing,
        semantic_contradiction=max((value.contradiction for value in semantics), default=0.0),
        semantic_neutral=max((value.neutral for value in semantics), default=0.0),
        hard_fail_count=hard_fail_count,
        soft_warning_count=soft_warning_count,
        mandate_currency=budget_constraint.currency if budget_constraint else cart.currency,
        cart_currency=cart.currency,
        category_mismatch=cart.merchant_category.upper() in prohibited_categories,
        domain=categories.get(cart.merchant_category, "retail"),
        merchant_category=cart.merchant_category,
        evidence_sufficiency="ambiguous" if missing else "sufficient",
    )


class HeuristicStructuredScorer:
    version = None
    catboost_version = None
    stacker_version = None
    calibrator_version = None
    step_up_threshold = None
    semantic_model_versions = None

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
    stacker_version = None
    calibrator_version = None
    step_up_threshold = None
    semantic_model_versions = None

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
        self.catboost_version = self.version

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


def _logistic_probability(bundle: dict, values: list[float]) -> float:
    raw = float(bundle["intercept"]) + sum(
        float(coefficient) * value for coefficient, value in zip(bundle["coefficients"], values, strict=True)
    )
    return 1.0 / (1.0 + math.exp(-max(min(raw, 40), -40)))


class FusionArtifactScorer(CatBoostArtifactScorer):
    def __init__(self, artifact_dir: Path, manifest_path: Path) -> None:
        manifest = json.loads(manifest_path.read_text())
        if not manifest.get("serving_approved"):
            raise RuntimeError("fusion artifact has not passed the explicit promotion gate")
        if manifest["feature_names"] != FEATURE_NAMES or manifest["feature_version"] != FEATURE_VERSION:
            raise RuntimeError("Fusion artifact feature schema is incompatible with this API build")
        base_path = artifact_dir / manifest["base_artifact"]
        fusion_path = artifact_dir / manifest["fusion_artifact"]
        if hashlib.sha256(base_path.read_bytes()).hexdigest() != manifest["base_sha256"]:
            raise RuntimeError("Fusion CatBoost checksum does not match its manifest")
        if hashlib.sha256(fusion_path.read_bytes()).hexdigest() != manifest["fusion_sha256"]:
            raise RuntimeError("Fusion bundle checksum does not match its manifest")
        from catboost import CatBoostClassifier

        self.model = CatBoostClassifier()
        self.model.load_model(base_path)
        self.bundle = json.loads(fusion_path.read_text())
        self.version = str(manifest["model_version"])
        self.catboost_version = str(manifest["catboost_version"])
        self.stacker_version = str(manifest["stacker_version"])
        self.calibrator_version = str(manifest["calibrator_version"])
        self.step_up_threshold = float(manifest["model_step_up_threshold"])
        self.semantic_model_versions = [str(value) for value in manifest["semantic_model_versions"]]
        if manifest.get("model_hold_enabled"):
            raise RuntimeError("model-only HOLD is prohibited until a pilot-approved policy enables it")

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
        catboost_probability = float(self.model.predict_proba(vector)[0][1])
        stack_values = [
            float(features["semantic_contradiction"]),
            float(features["semantic_neutral"]),
            catboost_probability,
            float(features["hard_fail_count"]),
            float(features["soft_warning_count"]),
        ]
        stacked = _logistic_probability(self.bundle["stacker"], stack_values)
        return _logistic_probability(self.bundle["calibrator"], [stacked])


@lru_cache(maxsize=1)
def configured_structured_scorer() -> StructuredScorer:
    fusion_manifest = Path(
        os.getenv(
            "ACE_FUSION_MANIFEST",
            "artifacts/models/fusion-v2.serving.manifest.json",
        )
    )
    if os.getenv("ACE_MODEL_MODE") == "artifact" and os.getenv("ACE_SEMANTIC_ARTIFACT") and fusion_manifest.exists():
        return FusionArtifactScorer(fusion_manifest.parent, fusion_manifest)
    artifact_value = os.getenv("ACE_CATBOOST_ARTIFACT")
    manifest_value = os.getenv("ACE_CATBOOST_MANIFEST")
    if artifact_value and manifest_value and os.getenv("ACE_MODEL_MODE") == "artifact":
        artifact, manifest = Path(artifact_value), Path(manifest_value)
        if artifact.exists() and manifest.exists():
            return CatBoostArtifactScorer(artifact, manifest)
    return HeuristicStructuredScorer()
