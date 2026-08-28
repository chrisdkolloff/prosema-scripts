"""Batch submit artefacts, audit_log, and status/lock widening.

Revision ID: 012_batch_submit_artefacts
Revises: 011_job_leases
Create Date: 2026-08-27

Adds source bytes/hash, approval and submit columns, row-level write
artefacts, a general audit_log, locked_by_registration on gruppen_audit,
and non_conforming_number_count on snapshots. Widens batch status to
include submitting and discarded.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_batch_submit_artefacts"
down_revision: Union[str, Sequence[str], None] = "011_job_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_NEW = (
    "status IN ('draft', 'approved', 'submitting', 'submitted', 'discarded')"
)
_STATUS_OLD = "status IN ('draft', 'approved', 'submitted')"

_AUDIT_ACTION_NEW = (
    "action IN ("
    "'created', 'renamed', 'deleted', 'restored', "
    "'alias_added', 'alias_removed', 'locked_by_backfill', 'locked_by_registration'"
    ")"
)
_AUDIT_ACTION_OLD = (
    "action IN ("
    "'created', 'renamed', 'deleted', 'restored', "
    "'alias_added', 'alias_removed', 'locked_by_backfill'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_article_batches_status", "article_batches", type_="check")
    op.create_check_constraint(
        "ck_article_batches_status",
        "article_batches",
        _STATUS_NEW,
    )

    op.add_column(
        "article_batches",
        sa.Column("source_bytes", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "article_batches",
        sa.Column("source_sha256", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_article_batches_source_sha256",
        "article_batches",
        ["source_sha256"],
    )
    op.add_column(
        "article_batches",
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "article_batches",
        sa.Column("approved_by_oid", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_batches",
        sa.Column("approved_by_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_batches",
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "article_batches",
        sa.Column("submitted_by_oid", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_batches",
        sa.Column("submitted_by_name", sa.Text(), nullable=True),
    )

    op.add_column(
        "article_batch_rows",
        sa.Column("approved_payload", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "article_batch_rows",
        sa.Column("weclapp_article_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_batch_rows",
        sa.Column("write_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_batch_rows",
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "article_batch_rows",
        sa.Column("submitted_by_oid", sa.Text(), nullable=True),
    )

    op.add_column(
        "article_snapshots",
        sa.Column(
            "non_conforming_number_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_oid", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_audit_log_entity",
        "audit_log",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_audit_log_occurred_at",
        "audit_log",
        ["occurred_at"],
    )

    op.drop_constraint("ck_gruppen_audit_action", "gruppen_audit", type_="check")
    op.create_check_constraint(
        "ck_gruppen_audit_action",
        "gruppen_audit",
        _AUDIT_ACTION_NEW,
    )


def downgrade() -> None:
    op.drop_constraint("ck_gruppen_audit_action", "gruppen_audit", type_="check")
    op.create_check_constraint(
        "ck_gruppen_audit_action",
        "gruppen_audit",
        _AUDIT_ACTION_OLD,
    )

    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_column("article_snapshots", "non_conforming_number_count")

    op.drop_column("article_batch_rows", "submitted_by_oid")
    op.drop_column("article_batch_rows", "submitted_at")
    op.drop_column("article_batch_rows", "write_error")
    op.drop_column("article_batch_rows", "weclapp_article_id")
    op.drop_column("article_batch_rows", "approved_payload")

    op.drop_column("article_batches", "submitted_by_name")
    op.drop_column("article_batches", "submitted_by_oid")
    op.drop_column("article_batches", "submitted_at")
    op.drop_column("article_batches", "approved_by_name")
    op.drop_column("article_batches", "approved_by_oid")
    op.drop_column("article_batches", "approved_at")
    op.drop_index("ix_article_batches_source_sha256", table_name="article_batches")
    op.drop_column("article_batches", "source_sha256")
    op.drop_column("article_batches", "source_bytes")

    op.drop_constraint("ck_article_batches_status", "article_batches", type_="check")
    op.create_check_constraint(
        "ck_article_batches_status",
        "article_batches",
        _STATUS_OLD,
    )
