from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Treatment(StrEnum):
    APPROVE = "APPROVE"
    STEP_UP = "STEP_UP"
    HOLD = "HOLD"


class ConstraintType(StrEnum):
    TOTAL_BUDGET = "total_budget"
    CURRENCY = "currency"
    SEMANTIC_ATTRIBUTE = "semantic_attribute"
    ROUTE = "route"
    TRAVEL_DATES = "travel_dates"
    PROHIBITED_ITEM = "prohibited_item"
    PROHIBITED_CATEGORY = "prohibited_category"
    ALLOWED_MERCHANT = "allowed_merchant"
    MAX_FULFILLMENTS = "max_fulfillments"


class Operator(StrEnum):
    LTE = "lte"
    EQ = "eq"
    REQUIRED = "required"
    PROHIBITED = "prohibited"
    IN = "in"


class Constraint(StrictModel):
    constraint_id: str = Field(min_length=1, max_length=100)
    type: ConstraintType
    operator: Operator
    value: Any | None = None
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    source_span: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_budget(self) -> Constraint:
        if self.type == ConstraintType.TOTAL_BUDGET and (
            self.amount_minor is None or self.currency is None
        ):
            raise ValueError("total_budget requires amount_minor and currency")
        return self


class ApprovalPolicy(StrictModel):
    allow_step_up: bool = True
    allow_agent_override: bool = False


class MandateProposal(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    mandate_id: str
    mandate_version: int = Field(default=1, ge=1)
    principal_id: str
    agent_id: str
    objective_text: str = Field(min_length=10, max_length=5000)
    constraints: list[Constraint] = Field(min_length=1)
    valid_from: datetime
    expires_at: datetime
    max_fulfillments: int = Field(default=1, ge=1, le=100)
    approval_policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)

    @model_validator(mode="after")
    def validate_window(self) -> MandateProposal:
        if self.valid_from.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("mandate timestamps must include a timezone")
        if self.expires_at <= self.valid_from:
            raise ValueError("expires_at must be after valid_from")
        ids = [constraint.constraint_id for constraint in self.constraints]
        if len(ids) != len(set(ids)):
            raise ValueError("constraint IDs must be unique")
        return self


class InterpretMandateRequest(StrictModel):
    objective_text: str = Field(min_length=10, max_length=5000)
    principal_id: str = "cm_demo_001"
    agent_id: str = "agent_demo_travel"
    market_timezone: str = "Asia/Singapore"


class InterpretationResponse(StrictModel):
    proposal: MandateProposal
    warnings: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True
    interpreter_version: str = "deterministic-v1"


class ConfirmMandateRequest(StrictModel):
    proposal: MandateProposal
    confirmed: bool


class Mandate(MandateProposal):
    authorization_reference: str
    authenticated_at: datetime
    status: str = "active"
    superseded_mandate_reference: str | None = None


class MandateState(StrictModel):
    mandate_id: str
    current_version: int
    status: str
    fulfilled_amount_minor: int = 0
    fulfillment_count: int = 0
    prior_transaction_ids: list[str] = Field(default_factory=list)
    last_updated_at: datetime


class MandateView(StrictModel):
    mandate: Mandate
    state: MandateState


class RevocationResponse(StrictModel):
    mandate_id: str
    status: Literal["revoked"]
    created_at: datetime


class LineItem(StrictModel):
    line_item_id: str
    description: str = Field(min_length=1, max_length=2000)
    evidence_text: str = Field(default="", max_length=5000)
    quantity: int = Field(ge=1, le=10000)
    amount_minor: int = Field(ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class CartEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    cart_id: str
    merchant_id: str
    merchant_category: str
    evidence_source: str
    evidence_trust: str
    evidence_sufficiency: Literal["sufficient", "ambiguous", "missing"] = "sufficient"
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    total_amount_minor: int = Field(ge=0)
    line_items: list[LineItem] = Field(min_length=1)
    created_at: datetime
    evidence_reference: str

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_line_items(self) -> CartEvidence:
        ids = [item.line_item_id for item in self.line_items]
        if len(ids) != len(set(ids)):
            raise ValueError("line item IDs must be unique")
        line_total = sum(item.amount_minor * item.quantity for item in self.line_items)
        if line_total != self.total_amount_minor:
            raise ValueError("cart total must equal the sum of line item amounts and quantities")
        return self


class EvaluateDecisionRequest(StrictModel):
    mandate_id: str
    cart: CartEvidence


class RuleStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class RuleResult(StrictModel):
    rule_id: str
    status: RuleStatus
    severity: str
    observed_value: Any | None = None
    expected_value: Any | None = None
    evidence_reference: str | None = None
    reason_code: str | None = None


class SemanticResult(StrictModel):
    constraint_id: str
    contradiction: float = Field(ge=0, le=1)
    entailment: float = Field(ge=0, le=1)
    neutral: float = Field(ge=0, le=1)
    evidence_reference: str


class ModelVersions(StrictModel):
    semantic: str
    catboost: str | None = None
    tabm: str | None = None
    stacker: str | None = None
    calibrator: str | None = None
    policy: str
    features: str
    runtime_mode: str = "heuristic"
    candidate_status: str | None = None
    model_step_up_threshold: float | None = Field(default=None, ge=0, le=1)


class RuntimeStatus(StrictModel):
    runtime_mode: str
    ready: bool
    semantic: str
    catboost: str | None = None
    calibrator: str | None = None
    policy: str
    features: str
    candidate_status: str | None = None
    model_step_up_threshold: float | None = Field(default=None, ge=0, le=1)
    evidence_verification: str


class DecisionResponse(StrictModel):
    decision_id: str
    mandate_id: str
    cart_id: str
    treatment: Treatment
    risk_probability: float = Field(ge=0, le=1)
    structured_risk_probability: float = Field(ge=0, le=1)
    uncertainty_band: str
    reason_codes: list[str]
    card_member_explanation: str
    reviewer_explanation: str
    rule_results: list[RuleResult]
    semantic_results: list[SemanticResult]
    model_versions: ModelVersions
    evidence_references: list[str]
    created_at: datetime


class ResolutionAction(StrEnum):
    APPROVE_ONCE = "APPROVE_ONCE"
    MODIFY_MANDATE = "MODIFY_MANDATE"
    DECLINE = "DECLINE"


class ResolveDecisionRequest(StrictModel):
    action: ResolutionAction
    modified_proposal: MandateProposal | None = None

    @model_validator(mode="after")
    def modified_proposal_required(self) -> ResolveDecisionRequest:
        if self.action == ResolutionAction.MODIFY_MANDATE and self.modified_proposal is None:
            raise ValueError("modified_proposal is required for MODIFY_MANDATE")
        return self


class ResolutionResponse(StrictModel):
    decision_id: str
    action: ResolutionAction
    status: str
    mandate_id: str
    new_mandate_id: str | None = None
    created_at: datetime


class AuditEvent(StrictModel):
    event_id: str
    session_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class AuditTimeline(StrictModel):
    session_id: str
    events: list[AuditEvent]


class EvaluationSummary(StrictModel):
    dataset_version: str
    model_version: str
    status: str
    metrics: dict[str, float]
    attack_families: dict[str, dict[str, float]]
    latency_ms: dict[str, float]
    generated_at: datetime


class ErrorDetail(StrictModel):
    code: str
    message: str
    correlation_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(StrictModel):
    error: ErrorDetail


def utc_now() -> datetime:
    return datetime.now(UTC)
