from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class MandateRecord(Base):
    __tablename__ = "mandates"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    principal_id: Mapped[str] = mapped_column(String(100), index=True)
    agent_id: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(Text)
    authorization_reference: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="active")
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MandateStateRecord(Base):
    __tablename__ = "mandate_state"

    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), primary_key=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active")
    fulfilled_amount_minor: Mapped[int] = mapped_column(Integer, default=0)
    fulfillment_count: Mapped[int] = mapped_column(Integer, default=0)
    prior_transaction_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    row_version: Mapped[int] = mapped_column(Integer, default=0)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MandateConstraintRecord(Base):
    __tablename__ = "mandate_constraints"
    __table_args__ = (
        UniqueConstraint("mandate_id", "constraint_id", name="uq_mandate_constraint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), index=True)
    constraint_id: Mapped[str] = mapped_column(String(100))
    constraint_type: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[str] = mapped_column(Text)


class CartRecord(Base):
    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CartLineItemRecord(Base):
    __tablename__ = "cart_line_items"
    __table_args__ = (UniqueConstraint("cart_id", "line_item_id", name="uq_cart_line_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"), index=True)
    line_item_id: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(Text)


class DecisionRecord(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), index=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"))
    treatment: Mapped[str] = mapped_column(String(30))
    response_json: Mapped[str] = mapped_column(Text)
    resolved_action: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DecisionSignalRecord(Base):
    __tablename__ = "decision_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(50))
    signal_key: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(Text)


class ResolutionRecord(Base):
    __tablename__ = "resolutions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), unique=True)
    action: Mapped[str] = mapped_column(String(30))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelRegistryRecord(Base):
    __tablename__ = "model_registry"

    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(50))
    metadata_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
