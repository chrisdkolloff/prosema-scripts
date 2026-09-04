"""Transform preview tables.

Revision ID: 018_transform_preview
Revises: 017_assistant_query_selection
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "018_transform_preview"
down_revision: Union[str, Sequence[str], None] = "017_assistant_query_selection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transform_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_by_oid", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('previewing', 'previewed', 'failed')",
            name="ck_transform_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["article_snapshots.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_transform_runs_created_at", "transform_runs", ["created_at"])
    op.create_index("ix_transform_runs_snapshot", "transform_runs", ["snapshot_id"])

    op.create_table(
        "transform_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_number", sa.Text(), nullable=False),
        sa.Column("weclapp_id", sa.Text(), nullable=False),
        sa.Column("version_at_preview", sa.Text(), nullable=True),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column(
            "operations_fired",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("row_status", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "row_status IN ('CHANGED', 'UNCHANGED', 'REFUSED', 'GONE')",
            name="ck_transform_rows_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["transform_runs.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_transform_rows_run", "transform_rows", ["run_id"])
    op.create_index(
        "ix_transform_rows_run_article",
        "transform_rows",
        ["run_id", "article_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_transform_rows_run_article", table_name="transform_rows")
    op.drop_index("ix_transform_rows_run", table_name="transform_rows")
    op.drop_table("transform_rows")
    op.drop_index("ix_transform_runs_snapshot", table_name="transform_runs")
    op.drop_index("ix_transform_runs_created_at", table_name="transform_runs")
    op.drop_table("transform_runs")
