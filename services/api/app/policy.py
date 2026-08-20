from __future__ import annotations

from dataclasses import dataclass

from .schemas import RuleResult, RuleStatus, SemanticResult, Treatment
from .treatment_contract import treatment_for_signals


@dataclass(frozen=True)
class PolicyDecision:
    treatment: Treatment
    risk_probability: float
    uncertainty_band: str
    reason_codes: list[str]


def apply_policy(
    rules: list[RuleResult],
    semantics: list[SemanticResult],
    structured_probability: float | None = None,
    model_step_up_threshold: float | None = None,
) -> PolicyDecision:
    reason_codes = [result.reason_code for result in rules if result.reason_code]
    reason_codes.extend("REQUIRED_ATTRIBUTE_CONTRADICTED" for result in semantics if result.contradiction >= 0.8)
    reason_codes.extend("REQUIRED_ATTRIBUTE_EVIDENCE_MISSING" for result in semantics if result.neutral >= 0.6)
    reason_codes = list(dict.fromkeys(reason_codes))

    not_evaluable = any(result.status == RuleStatus.NOT_EVALUABLE for result in rules)
    commercial_failure = any(result.status == RuleStatus.FAIL for result in rules)
    semantic_contradiction = any(result.contradiction >= 0.8 for result in semantics)
    semantic_uncertainty = any(result.neutral >= 0.6 for result in semantics)
    model_escalation = bool(
        model_step_up_threshold is not None
        and structured_probability is not None
        and structured_probability >= model_step_up_threshold
    )
    treatment = treatment_for_signals(
        reason_codes,
        has_unclassified_failure=commercial_failure or semantic_contradiction,
        has_not_evaluable=not_evaluable or semantic_uncertainty,
        model_escalation=model_escalation,
    )
    if treatment == Treatment.HOLD:
        return PolicyDecision(Treatment.HOLD, 0.99, "high", reason_codes)
    if model_escalation:
        reason_codes.append("MODEL_RISK_THRESHOLD_EXCEEDED")
    if treatment == Treatment.STEP_UP:
        probability = max(structured_probability or 0.55, 0.55)
        return PolicyDecision(Treatment.STEP_UP, probability, "moderate", reason_codes)

    probability = structured_probability if structured_probability is not None else 0.05
    band = "low" if probability < 0.3 else "moderate"
    return PolicyDecision(Treatment.APPROVE, probability, band, reason_codes)
