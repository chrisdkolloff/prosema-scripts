"""Audit log for article-assistant questions.

Revision ID: 014_assistant_queries
Revises: 013_article_templates
Create Date: 2026-08-31

Survives snapshot retention via ON DELETE SET NULL on snapshot_id.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_assistant_queries"
down_revision: Union[str, Sequence[str], None] = "013_article_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "asked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("user_oid", sa.Text(), nullable=False),
        sa.Column("user_name", sa.Text(), nullable=False),
        sa.Column("question_de", sa.Text(), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("answer_de", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=True),
        sa.Column("turns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["article_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "outcome IN ("
            "'answered','answered_unverified','no_result',"
            "'refused','error','unavailable'"
            ")",
            name="ck_assistant_queries_outcome",
        ),
    )
    op.create_index("ix_assistant_queries_asked_at", "assistant_queries", ["asked_at"])


def downgrade() -> None:
    op.drop_index("ix_assistant_queries_asked_at", table_name="assistant_queries")
    op.drop_table("assistant_queries")
