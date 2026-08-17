"""Initial Mandate Assurance persistence model.

Revision ID: 0001
Revises:
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mandates",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("principal_id", sa.String(length=100), nullable=False),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("authorization_reference", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mandates_principal_id", "mandates", ["principal_id"])
    op.create_table(
        "mandate_state",
        sa.Column("mandate_id", sa.String(length=100), sa.ForeignKey("mandates.id"), primary_key=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("fulfilled_amount_minor", sa.Integer(), nullable=False),
        sa.Column("fulfillment_count", sa.Integer(), nullable=False),
        sa.Column("prior_transaction_ids_json", sa.Text(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mandate_constraints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mandate_id", sa.String(length=100), sa.ForeignKey("mandates.id"), nullable=False),
        sa.Column("constraint_id", sa.String(length=100), nullable=False),
        sa.Column("constraint_type", sa.String(length=50), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("mandate_id", "constraint_id", name="uq_mandate_constraint"),
    )
    op.create_index("ix_mandate_constraints_mandate_id", "mandate_constraints", ["mandate_id"])
    op.create_table(
        "carts",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("mandate_id", sa.String(length=100), sa.ForeignKey("mandates.id"), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_carts_mandate_id", "carts", ["mandate_id"])
    op.create_table(
        "cart_line_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cart_id", sa.String(length=100), sa.ForeignKey("carts.id"), nullable=False),
        sa.Column("line_item_id", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("cart_id", "line_item_id", name="uq_cart_line_item"),
    )
    op.create_index("ix_cart_line_items_cart_id", "cart_line_items", ["cart_id"])
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("mandate_id", sa.String(length=100), sa.ForeignKey("mandates.id"), nullable=False),
        sa.Column("cart_id", sa.String(length=100), sa.ForeignKey("carts.id"), nullable=False),
        sa.Column("treatment", sa.String(length=30), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("resolved_action", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decisions_mandate_id", "decisions", ["mandate_id"])
    op.create_table(
        "decision_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=100), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("signal_key", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_decision_signals_decision_id", "decision_signals", ["decision_id"])
    op.create_table(
        "resolutions",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("decision_id", sa.String(length=100), sa.ForeignKey("decisions.id"), nullable=False, unique=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
    )
    op.create_table(
        "model_registry",
        sa.Column("version", sa.String(length=100), primary_key=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("model_registry")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("resolutions")
    op.drop_index("ix_decision_signals_decision_id", table_name="decision_signals")
    op.drop_table("decision_signals")
    op.drop_index("ix_decisions_mandate_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_cart_line_items_cart_id", table_name="cart_line_items")
    op.drop_table("cart_line_items")
    op.drop_index("ix_carts_mandate_id", table_name="carts")
    op.drop_table("carts")
    op.drop_index("ix_mandate_constraints_mandate_id", table_name="mandate_constraints")
    op.drop_table("mandate_constraints")
    op.drop_table("mandate_state")
    op.drop_index("ix_mandates_principal_id", table_name="mandates")
    op.drop_table("mandates")

