"""Transform apply: case-variant warnings, chunks, per-row apply outcome.

Revision ID: 019_transform_apply
Revises: 018_transform_preview
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019_transform_apply"
down_revision: Union[str, Sequence[str], None] = "018_transform_preview"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transform_runs",
        sa.Column(
            "case_variants",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "transform_rows",
        sa.Column("apply_outcome", sa.Text(), nullable=True),
    )
    op.add_column(
        "transform_rows",
        sa.Column("apply_detail", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "transform_rows",
        sa.Column("apply_version_seen", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_transform_rows_apply_outcome",
        "transform_rows",
        "apply_outcome IS NULL OR apply_outcome IN ("
        "'UPDATED','UNCHANGED','CONFLICT','REJECTED','GONE',"
        "'REFUSED','UNAVAILABLE'"
        ")",
    )
    op.create_table(
        "transform_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("row_ids", postgresql.JSONB(), nullable=False),
        sa.Column("approved_by_oid", sa.Text(), nullable=False),
        sa.Column(
            "approved_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('approved', 'applying', 'applied', 'failed')",
            name="ck_transform_chunks_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["transform_runs.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "chunk_index", name="uq_transform_chunks_run_index"),
    )
    op.create_index("ix_transform_chunks_run", "transform_chunks", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_transform_chunks_run", table_name="transform_chunks")
    op.drop_table("transform_chunks")
    op.drop_constraint(
        "ck_transform_rows_apply_outcome",
        "transform_rows",
        type_="check",
    )
    op.drop_column("transform_rows", "apply_version_seen")
    op.drop_column("transform_rows", "apply_detail")
    op.drop_column("transform_rows", "apply_outcome")
    op.drop_column("transform_runs", "case_variants")
