"""Repair pre-Alembic mandate state concurrency metadata.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("mandate_state")}
    if "row_version" not in columns:
        with op.batch_alter_table("mandate_state") as batch:
            batch.add_column(
                sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("0"))
            )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("mandate_state")}
    if "row_version" in columns:
        with op.batch_alter_table("mandate_state") as batch:
            batch.drop_column("row_version")
