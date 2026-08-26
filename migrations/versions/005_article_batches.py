"""Article registration batches and grid edit rows.

Revision ID: 005_article_batches
Revises: 004_user_weclapp_tokens
Create Date: 2026-08-25

raw_data is the immutable upload. Cell edits land in edits. Presence is
advisory only (last write wins per cell).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_article_batches"
down_revision: Union[str, Sequence[str], None] = "004_user_weclapp_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("created_by_oid", sa.Text(), nullable=False),
        sa.Column("created_by_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'submitted')",
            name="ck_article_batches_status",
        ),
    )
    op.create_table(
        "article_batch_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "edits",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("proposed_article_number", sa.Text(), nullable=False, server_default=""),
        sa.Column("include", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("validation_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolved_hauptgruppe_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_untergruppe_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["article_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_hauptgruppe_id"],
            ["hauptgruppen.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_untergruppe_id"],
            ["untergruppen.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_article_batch_rows_batch_position",
        "article_batch_rows",
        ["batch_id", "position"],
    )
    op.create_table(
        "article_batch_presence",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_oid", sa.Text(), primary_key=True, nullable=False),
        sa.Column("user_name", sa.Text(), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["article_batches.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("article_batch_presence")
    op.drop_index("ix_article_batch_rows_batch_position", table_name="article_batch_rows")
    op.drop_table("article_batch_rows")
    op.drop_table("article_batches")
