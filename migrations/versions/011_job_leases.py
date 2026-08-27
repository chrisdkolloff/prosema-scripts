"""Add job lease columns for stale-running recovery.

Revision ID: 011_job_leases
Revises: 010_sales_article_number_always
Create Date: 2026-08-27

``attempts`` already exists from 001_create_jobs; this revision adds
``heartbeat_at`` and ``worker_id`` only.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_job_leases"
down_revision: Union[str, Sequence[str], None] = "010_sales_article_number_always"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("worker_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_jobs_status_heartbeat",
        "jobs",
        ["status", "heartbeat_at"],
    )
    # Make existing orphans visible to the stale-job sweep immediately.
    op.execute(
        "UPDATE jobs SET heartbeat_at = started_at "
        "WHERE status = 'running' AND heartbeat_at IS NULL"
    )
    op.execute(
        "UPDATE jobs SET attempts = 1 "
        "WHERE status IN ('running', 'succeeded', 'failed') AND attempts = 0"
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_status_heartbeat", table_name="jobs")
    op.drop_column("jobs", "worker_id")
    op.drop_column("jobs", "heartbeat_at")
