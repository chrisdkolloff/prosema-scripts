"""Supply-source templates, uploads, run FKs, and row divergence fields.

Revision ID: 031_supply_source_upload
Revises: 030_article_unit

Article templates use a UUID PK and store xlsx_bytes on the template row.
This revision uses serial PKs (same as supply_source_run) and stores the raw
upload on supply_source_uploads. The template is a column spec; XLSX is
generated on demand from the spec plus the mirror.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "031_supply_source_upload"
down_revision: Union[str, Sequence[str], None] = "030_article_unit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supply_source_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_by_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "supplier_id", "version", name="uq_supply_source_templates_supplier_version"
        ),
    )
    op.create_index(
        "uq_supply_source_templates_active",
        "supply_source_templates",
        ["supplier_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "supply_source_uploads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("supply_source_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "parse_summary",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("uploaded_by", sa.Text(), nullable=False),
        sa.Column("uploaded_by_name", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.add_column(
        "supply_source_run",
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("supply_source_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "supply_source_run",
        sa.Column(
            "upload_id",
            sa.Integer(),
            sa.ForeignKey("supply_source_uploads.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.add_column("supply_source_row", sa.Column("template_name", sa.Text(), nullable=True))
    op.add_column("supply_source_row", sa.Column("template_ean", sa.Text(), nullable=True))
    op.add_column(
        "supply_source_row",
        sa.Column("template_min_qty", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column("template_lead_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column(
            "field_overrides",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("supply_source_row", "field_overrides")
    op.drop_column("supply_source_row", "template_lead_days")
    op.drop_column("supply_source_row", "template_min_qty")
    op.drop_column("supply_source_row", "template_ean")
    op.drop_column("supply_source_row", "template_name")
    op.drop_column("supply_source_run", "upload_id")
    op.drop_column("supply_source_run", "template_id")
    op.drop_table("supply_source_uploads")
    op.drop_index(
        "uq_supply_source_templates_active", table_name="supply_source_templates"
    )
    op.drop_table("supply_source_templates")
