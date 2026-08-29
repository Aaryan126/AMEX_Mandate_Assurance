from __future__ import annotations

import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from .feature_contract import (
    FEATURE_VERSION,
    feature_profile_for_names,
    feature_values,
    stack_feature_names_for_profile,
)
from .schemas import CartEvidence, Mandate, MandateState, RuleResult, RuleStatus, SemanticResult

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class StructuredScorer(Protocol):
    version: str | None
    catboost_version: str | None
    stacker_version: str | None
    calibrator_version: str | None
    step_up_threshold: float | None
    semantic_model_versions: list[str] | None
    runtime_mode: str
    candidate_status: str | None

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
    runtime_only_rules = {
        "mandate_signature",
        "mandate_status",
        "mandate_window",
        "trusted_evidence",
        "cart_replay",
    }
    commercial_results = [result for result in rules if result.rule_id not in runtime_only_rules]
    hard_fail_count = sum(result.status == RuleStatus.FAIL for result in commercial_results)
    categories = {"AIRLINE": "travel", "HOTEL": "travel", "RESTAURANT": "dining"}
    missing = int(cart.evidence_sufficiency != "sufficient")
    soft_warning_count = missing
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
        evidence_sufficiency=cart.evidence_sufficiency,
    )


class HeuristicStructuredScorer:
    version = None
    catboost_version = None
    stacker_version = None
    calibrator_version = None
    step_up_threshold = None
    semantic_model_versions = None
    runtime_mode = "heuristic"
    candidate_status = None

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
    runtime_mode = "artifact"
    candidate_status = None

    def __init__(self, artifact_path: Path, manifest_path: Path) -> None:
        from catboost import CatBoostClassifier

        manifest = json.loads(manifest_path.read_text())
        feature_names = [str(value) for value in manifest["feature_names"]]
        feature_profile = feature_profile_for_names(feature_names)
        if manifest.get("feature_profile", feature_profile) != feature_profile:
            raise RuntimeError("CatBoost artifact feature profile is inconsistent")
        if manifest["feature_version"] != FEATURE_VERSION:
            raise RuntimeError("CatBoost artifact feature schema is incompatible with this API build")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if checksum != manifest["artifact_sha256"]:
            raise RuntimeError("CatBoost artifact checksum does not match its manifest")
        self.model = CatBoostClassifier()
        self.model.load_model(artifact_path)
        self.version = str(manifest["model_version"])
        self.catboost_version = self.version
        self.semantic_model_versions = [str(value) for value in manifest.get("semantic_model_versions", [])] or None
        self.feature_names = feature_names
        self.feature_profile = feature_profile

    def score(
        self,
        mandate: Mandate,
        state: MandateState,
        cart: CartEvidence,
        rules: list[RuleResult],
        semantics: list[SemanticResult],
    ) -> float:
        features = runtime_features(mandate, state, cart, rules, semantics)
        vector = [[features[name] for name in self.feature_names]]
        return float(self.model.predict_proba(vector)[0][1])


class DevelopmentV3ArtifactScorer(CatBoostArtifactScorer):
    runtime_mode = "development_artifact"
    stacker_version = None

    def __init__(
        self,
        artifact_path: Path,
        manifest_path: Path,
        calibrator_path: Path,
        candidate_lock_path: Path,
    ) -> None:
        lock = json.loads(candidate_lock_path.read_text())
        if lock.get("lock_version") != "candidate-lock-v3":
            raise RuntimeError("development artifact requires the v3 candidate lock")
        if lock.get("selected_candidate") != "calibrated_catboost":
            raise RuntimeError("candidate lock does not select calibrated CatBoost")
        bindings = lock.get("bindings", {})
        expected = {
            "catboost_model_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "catboost_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "calibrator_sha256": hashlib.sha256(calibrator_path.read_bytes()).hexdigest(),
        }
        for key, actual in expected.items():
            if bindings.get(key) != actual:
                raise RuntimeError(f"candidate lock {key} does not match the configured artifact")
        baseline_path = Path(str(bindings.get("baseline_report", "")))
        if not baseline_path.is_absolute():
            baseline_path = REPOSITORY_ROOT / baseline_path
        if not baseline_path.is_file():
            raise RuntimeError("candidate lock baseline report is unavailable")
        if hashlib.sha256(baseline_path.read_bytes()).hexdigest() != bindings.get("baseline_report_sha256"):
            raise RuntimeError("candidate lock baseline report checksum is invalid")
        baseline = json.loads(baseline_path.read_text())
        selected_threshold = baseline["candidates"]["calibrated_catboost"]["threshold_selection"]["threshold"]
        if not math.isclose(float(lock["policy_threshold"]), float(selected_threshold), rel_tol=0, abs_tol=1e-12):
            raise RuntimeError("candidate lock threshold does not match the baseline report")

        super().__init__(artifact_path, manifest_path)
        try:
            from joblib import load
        except ImportError as exc:
            raise RuntimeError(
                "Install services/api[model-runtime] to load the v3 Platt calibrator"
            ) from exc
        self.calibrator = load(calibrator_path)
        if not hasattr(self.calibrator, "predict_proba"):
            raise RuntimeError("configured v3 calibrator does not expose predict_proba")
        self.calibrator_version = "platt-calibrator-v3"
        self.step_up_threshold = float(lock["policy_threshold"])
        self.candidate_status = str(lock["status"])
        self.version = f"{self.catboost_version} + {self.calibrator_version}"

    def score(
        self,
        mandate: Mandate,
        state: MandateState,
        cart: CartEvidence,
        rules: list[RuleResult],
        semantics: list[SemanticResult],
    ) -> float:
        raw_probability = super().score(mandate, state, cart, rules, semantics)
        bounded = min(max(raw_probability, 1e-6), 1 - 1e-6)
        logit = math.log(bounded / (1 - bounded))
        return float(self.calibrator.predict_proba([[logit]])[0][1])


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
        feature_names = [str(value) for value in manifest["feature_names"]]
        feature_profile = feature_profile_for_names(feature_names)
        if manifest.get("feature_profile", feature_profile) != feature_profile:
            raise RuntimeError("Fusion artifact feature profile is inconsistent")
        if manifest["feature_version"] != FEATURE_VERSION:
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
        self.runtime_mode = "artifact"
        self.candidate_status = "SERVING_APPROVED"
        self.feature_names = feature_names
        self.feature_profile = feature_profile
        self.stack_features = [str(value) for value in manifest["stack_features"]]
        if self.stack_features != stack_feature_names_for_profile(feature_profile):
            raise RuntimeError("Fusion artifact stack feature profile is incompatible")
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
        vector = [[features[name] for name in self.feature_names]]
        catboost_probability = float(self.model.predict_proba(vector)[0][1])
        stack_source = {**features, "catboost_probability": catboost_probability}
        stack_values = [float(stack_source[name]) for name in self.stack_features]
        stacked = _logistic_probability(self.bundle["stacker"], stack_values)
        return _logistic_probability(self.bundle["calibrator"], [stacked])


@lru_cache(maxsize=1)
def configured_structured_scorer() -> StructuredScorer:
    model_mode = os.getenv("ACE_MODEL_MODE", "heuristic")
    if model_mode == "development_artifact":
        artifact = Path(
            os.getenv(
                "ACE_CATBOOST_ARTIFACT",
                str(REPOSITORY_ROOT / "artifacts/models/development-v3-catboost/catboost-v1.cbm"),
            )
        )
        manifest = Path(
            os.getenv(
                "ACE_CATBOOST_MANIFEST",
                str(
                    REPOSITORY_ROOT
                    / "artifacts/models/development-v3-catboost/catboost-v1.manifest.json"
                ),
            )
        )
        calibrator = Path(
            os.getenv(
                "ACE_CALIBRATOR_ARTIFACT",
                str(
                    REPOSITORY_ROOT
                    / "artifacts/models/development-v3-baselines/platt-calibrator-v3.joblib"
                ),
            )
        )
        candidate_lock = Path(
            os.getenv(
                "ACE_CANDIDATE_LOCK",
                str(REPOSITORY_ROOT / "artifacts/models/development-v3-baselines/candidate-lock.json"),
            )
        )
        missing = [str(path) for path in (artifact, manifest, calibrator, candidate_lock) if not path.is_file()]
        if missing:
            raise RuntimeError(f"development artifact runtime is missing required files: {', '.join(missing)}")
        return DevelopmentV3ArtifactScorer(artifact, manifest, calibrator, candidate_lock)

    fusion_manifest = Path(
        os.getenv(
            "ACE_FUSION_MANIFEST",
            "artifacts/models/fusion-v2.serving.manifest.json",
        )
    )
    if model_mode == "artifact" and os.getenv("ACE_SEMANTIC_ARTIFACT") and fusion_manifest.exists():
        return FusionArtifactScorer(fusion_manifest.parent, fusion_manifest)
    artifact_value = os.getenv("ACE_CATBOOST_ARTIFACT")
    manifest_value = os.getenv("ACE_CATBOOST_MANIFEST")
    if artifact_value and manifest_value and model_mode == "artifact":
        artifact, manifest = Path(artifact_value), Path(manifest_value)
        if artifact.exists() and manifest.exists():
            return CatBoostArtifactScorer(artifact, manifest)
    return HeuristicStructuredScorer()
