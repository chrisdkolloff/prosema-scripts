"""Article templates table, seed v1, pin batches to template.

Revision ID: 013_article_templates
Revises: 012_batch_submit_artefacts
Create Date: 2026-08-27

Immutable versioned upload templates. Seeded v1 from the catalogue.
Existing batches are backfilled to v1. There is never a moment without
an active template.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013_article_templates"
down_revision: Union[str, Sequence[str], None] = "012_batch_submit_artefacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _seed_xlsx_and_columns() -> tuple[bytes, list[dict], str]:
    from app.excel_export import build_template_workbook
    from core.article_fields import FIELDS, seed_template_columns

    headers = [field.label for field in FIELDS]
    examples = {field.label: field.example for field in FIELDS}
    data = build_template_workbook(headers, examples=examples)
    columns = seed_template_columns()
    digest = hashlib.sha256(data).hexdigest()
    return data, columns, digest


def upgrade() -> None:
    op.create_table(
        "article_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("xlsx_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_oid", sa.Text(), nullable=True),
        sa.Column("created_by_name", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.UniqueConstraint("version", name="uq_article_templates_version"),
    )
    op.create_index(
        "uq_article_templates_active",
        "article_templates",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    xlsx_bytes, columns, digest = _seed_xlsx_and_columns()
    template_id = uuid.uuid4()
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO article_templates (
                id, version, is_active, columns, xlsx_bytes, sha256,
                created_by_oid, created_by_name, note
            ) VALUES (
                :id, 1, true, CAST(:columns AS jsonb), :xlsx_bytes, :sha256,
                NULL, 'System',
                'Initiale Vorlage aus dem bestehenden Import-Template.'
            )
            """
        ),
        {
            "id": template_id,
            "columns": json.dumps(columns),
            "xlsx_bytes": xlsx_bytes,
            "sha256": digest,
        },
    )

    op.add_column(
        "article_batches",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    conn.execute(
        sa.text("UPDATE article_batches SET template_id = :tid WHERE template_id IS NULL"),
        {"tid": template_id},
    )
    op.alter_column(
        "article_batches",
        "template_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_article_batches_template_id",
        "article_batches",
        "article_templates",
        ["template_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_article_batches_template_id",
        "article_batches",
        type_="foreignkey",
    )
    op.drop_column("article_batches", "template_id")
    op.drop_index("uq_article_templates_active", table_name="article_templates")
    op.drop_table("article_templates")
