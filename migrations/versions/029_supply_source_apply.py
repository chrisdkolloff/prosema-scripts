"""Apply columns for supply-source writes, plus alias audit.

Revision ID: 029_supply_source_apply
Revises: 028_supply_source_pipeline

created_supply_source_id is the durable midpoint of two-phase create:
POST the supply source, commit this id, then attach on the article.
A crash between those steps must not POST a second supply source.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "029_supply_source_apply"
down_revision: Union[str, Sequence[str], None] = "028_supply_source_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OUTCOMES = (
    "UPDATED",
    "PRICE_UPDATED",
    "UNCHANGED",
    "CREATED",
    "ATTACHED",
    "RENUMBERED",
    "CONFLICT",
    "REJECTED",
    "GONE",
    "AUTH",
    "UNKNOWN",
)


def upgrade() -> None:
    op.add_column(
        "supply_source_row",
        sa.Column("created_supply_source_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column("apply_outcome", sa.Text(), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column("apply_detail", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column("applied_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column("chunk_id", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_supply_source_row_apply_outcome",
        "supply_source_row",
        "apply_outcome IS NULL OR apply_outcome IN ("
        + ",".join(repr(v) for v in _OUTCOMES)
        + ")",
    )

    op.add_column(
        "supply_source_run",
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "supply_source_run",
        sa.Column("approved_by", sa.Text(), nullable=True),
    )
    op.add_column(
        "supply_source_run",
        sa.Column("applied_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "supply_source_run",
        sa.Column(
            "chunk_size",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
    )

    op.create_table(
        "supplier_article_aliases_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_oid", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.Text(), nullable=False),
        sa.Column(
            "at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "entity IN ('alias')",
            name="ck_supplier_article_aliases_audit_entity",
        ),
        sa.CheckConstraint(
            "action IN ('created', 'updated')",
            name="ck_supplier_article_aliases_audit_action",
        ),
    )


def downgrade() -> None:
    op.drop_table("supplier_article_aliases_audit")
    op.drop_column("supply_source_run", "chunk_size")
    op.drop_column("supply_source_run", "applied_at")
    op.drop_column("supply_source_run", "approved_by")
    op.drop_column("supply_source_run", "approved_at")
    op.drop_constraint(
        "ck_supply_source_row_apply_outcome",
        "supply_source_row",
        type_="check",
    )
    op.drop_column("supply_source_row", "chunk_id")
    op.drop_column("supply_source_row", "applied_at")
    op.drop_column("supply_source_row", "apply_detail")
    op.drop_column("supply_source_row", "apply_outcome")
    op.drop_column("supply_source_row", "created_supply_source_id")
