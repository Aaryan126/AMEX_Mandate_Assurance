from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATASET_SCHEMA_VERSION = "2.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceOrigin(StrEnum):
    REAL_PUBLIC = "real_public"
    SYNTHETIC = "synthetic"
    REAL_PRIVATE = "real_private"
    HYBRID_GROUNDED = "hybrid_grounded"


class MandateOrigin(StrEnum):
    SOURCE_QUERY = "source_query"
    HUMAN_AUTHORED = "human_authored"
    SYNTHETIC_TEMPLATE = "synthetic_template"


class DeviationLabel(StrEnum):
    MATCH = "MATCH"
    VIOLATION = "VIOLATION"
    AMBIGUOUS = "AMBIGUOUS"


class SemanticLabel(StrEnum):
    ENTAILMENT = "ENTAILMENT"
    CONTRADICTION = "CONTRADICTION"
    NEUTRAL = "NEUTRAL"


class ExpectedTreatment(StrEnum):
    APPROVE = "APPROVE"
    STEP_UP = "STEP_UP"
    HOLD = "HOLD"


class Identity(StrictModel):
    example_id: str = Field(min_length=1, max_length=160)
    group_id: str = Field(min_length=1, max_length=160)
    parent_example_id: str | None = Field(default=None, max_length=160)
    sequence_id: str | None = Field(default=None, max_length=160)
    sequence_position: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def sequence_fields_are_paired(self) -> Identity:
        if (self.sequence_id is None) != (self.sequence_position is None):
            raise ValueError(
                "sequence_id and sequence_position must be provided together"
            )
        return self


class Provenance(StrictModel):
    source_dataset: str
    source_version: str
    source_record_id: str
    source_url: str
    source_license: str
    evidence_origin: EvidenceOrigin
    mandate_origin: MandateOrigin
    transformation: str = "none"
    generator_version: str | None = None
    acquired_at: datetime | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    field_origins: dict[str, str] = Field(default_factory=dict)


class Context(StrictModel):
    domain: str
    locale: str
    market: str
    occurred_at: datetime | None = None


class DatasetConstraint(StrictModel):
    constraint_id: str
    type: str
    operator: str
    value: Any | None = None
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    currency_exponent: int | None = Field(default=None, ge=0, le=3)
    source_span: str | None = None


class DatasetMandate(StrictModel):
    objective_text: str = Field(min_length=1)
    constraints: list[DatasetConstraint] = Field(min_length=1)
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    max_fulfillments: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def window_is_valid(self) -> DatasetMandate:
        if (self.valid_from is None) != (self.expires_at is None):
            raise ValueError("valid_from and expires_at must be provided together")
        if self.valid_from and self.expires_at and self.expires_at <= self.valid_from:
            raise ValueError("expires_at must be after valid_from")
        return self


class DatasetLineItem(StrictModel):
    line_item_id: str
    source_product_id: str | None = None
    description: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    amount_minor: int = Field(ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str = ""


class DatasetCart(StrictModel):
    cart_id: str
    merchant_id: str
    merchant_category: str
    evidence_source: str
    evidence_trust: Literal["trusted", "untrusted", "unknown"]
    evidence_sufficiency: Literal["sufficient", "ambiguous", "missing"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    currency_exponent: int = Field(ge=0, le=3)
    total_amount_minor: int = Field(ge=0)
    line_items: list[DatasetLineItem] = Field(min_length=1)

    @model_validator(mode="after")
    def total_matches_items(self) -> DatasetCart:
        total = sum(item.amount_minor * item.quantity for item in self.line_items)
        if total != self.total_amount_minor:
            raise ValueError("cart total must equal quantity-adjusted line item total")
        return self


class DatasetState(StrictModel):
    fulfilled_amount_minor: int = Field(default=0, ge=0)
    fulfillment_count: int = Field(default=0, ge=0)
    prior_transaction_ids: list[str] = Field(default_factory=list)
    history_available: bool = True


class SemanticAnnotation(StrictModel):
    constraint_id: str
    label: SemanticLabel
    confidence: float | None = Field(default=None, ge=0, le=1)


class DatasetLabels(StrictModel):
    deviation: DeviationLabel | None = None
    semantic: list[SemanticAnnotation] = Field(default_factory=list)
    violation_types: list[str] = Field(default_factory=list)
    expected_treatment: ExpectedTreatment | None = None
    label_source: Literal[
        "unreviewed",
        "weak_esci_mapping",
        "weak_session_transition",
        "deterministic_counterfactual",
        "expert_review",
        "adjudicated_review",
        "llm_consensus",
        "llm_adjudicated",
        "mixed_review",
    ] = "unreviewed"
    reviewer_confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def reviewed_labels_have_targets(self) -> DatasetLabels:
        if (
            self.label_source
            in {
                "expert_review",
                "adjudicated_review",
                "llm_consensus",
                "llm_adjudicated",
                "mixed_review",
            }
            and self.deviation is None
        ):
            raise ValueError("reviewed labels require a deviation label")
        return self


class DatasetSplit(StrictModel):
    name: Literal["train", "validation", "calibration", "golden", "unassigned"] = (
        "unassigned"
    )
    grouping_keys: list[str] = Field(default_factory=list)


class AceDatasetExample(StrictModel):
    schema_version: Literal["2.0"] = DATASET_SCHEMA_VERSION
    identity: Identity
    provenance: Provenance
    context: Context
    mandate: DatasetMandate
    cart: DatasetCart
    state: DatasetState = Field(default_factory=DatasetState)
    labels: DatasetLabels = Field(default_factory=DatasetLabels)
    split: DatasetSplit = Field(default_factory=DatasetSplit)

    @model_validator(mode="after")
    def parent_cannot_be_self(self) -> AceDatasetExample:
        if self.identity.parent_example_id == self.identity.example_id:
            raise ValueError("an example cannot be its own parent")
        return self
