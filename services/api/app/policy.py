from __future__ import annotations

from dataclasses import dataclass

from .schemas import RuleResult, RuleStatus, SemanticResult, Treatment

CRITICAL_HOLD_CODES = {
    "MANDATE_AUTHORIZATION_INVALID",
    "MANDATE_NOT_ACTIVE",
    "MANDATE_EXPIRED_OR_NOT_YET_VALID",
    "CART_REPLAY_DETECTED",
    "CUMULATIVE_BUDGET_EXCEEDED",
    "FULFILLMENT_LIMIT_EXCEEDED",
    "PROHIBITED_OR_UNRELATED_ITEM",
    "MERCHANT_NOT_AUTHORIZED",
}


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

    if any(code in CRITICAL_HOLD_CODES for code in reason_codes):
        return PolicyDecision(Treatment.HOLD, 0.99, "high", reason_codes)
    not_evaluable = any(result.status == RuleStatus.NOT_EVALUABLE for result in rules)
    commercial_failure = any(result.status == RuleStatus.FAIL for result in rules)
    semantic_contradiction = any(result.contradiction >= 0.8 for result in semantics)
    semantic_uncertainty = any(result.neutral >= 0.6 for result in semantics)
    model_escalation = bool(
        model_step_up_threshold is not None
        and structured_probability is not None
        and structured_probability >= model_step_up_threshold
    )
    if model_escalation:
        reason_codes.append("MODEL_RISK_THRESHOLD_EXCEEDED")
    if not_evaluable or commercial_failure or semantic_contradiction or semantic_uncertainty or model_escalation:
        probability = max(structured_probability or 0.55, 0.55)
        return PolicyDecision(Treatment.STEP_UP, probability, "moderate", reason_codes)

    probability = structured_probability if structured_probability is not None else 0.05
    band = "low" if probability < 0.3 else "moderate"
    return PolicyDecision(Treatment.APPROVE, probability, band, reason_codes)
