"""Immutable weclapp article snapshots for Artikel-Übersicht.

Revision ID: 006_article_snapshots
Revises: 005_article_batches
Create Date: 2026-08-25

Snapshot rows are write-once; extracted columns support cheap filtering.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_article_snapshots"
down_revision: Union[str, Sequence[str], None] = "005_article_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_oid", sa.Text(), nullable=False),
        sa.Column("created_by_name", sa.Text(), nullable=False),
        sa.Column("weclapp_tenant", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column(
            "columns",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('running', 'complete', 'failed')",
            name="ck_article_snapshots_status",
        ),
    )
    op.create_index(
        "ix_article_snapshots_tenant_created",
        "article_snapshots",
        ["weclapp_tenant", "created_at"],
    )
    op.create_table(
        "article_snapshot_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("article_number", sa.Text(), nullable=False, server_default=""),
        sa.Column("article_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("hauptgruppe_code", sa.Text(), nullable=False, server_default=""),
        sa.Column("untergruppe_code", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("weclapp_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("weclapp_version", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["article_snapshots.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_article_snapshot_rows_snapshot_position",
        "article_snapshot_rows",
        ["snapshot_id", "position"],
    )
    op.create_index(
        "ix_article_snapshot_rows_snapshot_hauptgruppe",
        "article_snapshot_rows",
        ["snapshot_id", "hauptgruppe_code"],
    )
    op.create_index(
        "ix_article_snapshot_rows_snapshot_untergruppe",
        "article_snapshot_rows",
        ["snapshot_id", "untergruppe_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_article_snapshot_rows_snapshot_untergruppe",
        table_name="article_snapshot_rows",
    )
    op.drop_index(
        "ix_article_snapshot_rows_snapshot_hauptgruppe",
        table_name="article_snapshot_rows",
    )
    op.drop_index(
        "ix_article_snapshot_rows_snapshot_position",
        table_name="article_snapshot_rows",
    )
    op.drop_table("article_snapshot_rows")
    op.drop_index("ix_article_snapshots_tenant_created", table_name="article_snapshots")
    op.drop_table("article_snapshots")
