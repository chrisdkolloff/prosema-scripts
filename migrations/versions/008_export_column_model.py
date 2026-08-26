"""Bezugsquellen-Export: column metadata, extras jsonb, per-user visibility.

Revision ID: 008_export_column_model
Revises: 007_supply_source_export
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.supply_export_fields import field_alias_seed_rows

revision: str = "008_export_column_model"
down_revision: Union[str, Sequence[str], None] = "007_supply_source_export"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("field_alias", sa.Column("scope", sa.Text(), nullable=True))
    op.add_column("field_alias", sa.Column("max_length", sa.Integer(), nullable=True))
    op.add_column(
        "field_alias",
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("field_alias", sa.Column("write_policy", sa.Text(), nullable=True))
    op.add_column("field_alias", sa.Column("edit_policy", sa.Text(), nullable=True))
    op.add_column(
        "field_alias",
        sa.Column(
            "default_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "field_alias",
        sa.Column("phase", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "field_alias",
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
    )

    op.execute("DELETE FROM field_alias")

    field_alias = sa.table(
        "field_alias",
        sa.column("field_key", sa.Text),
        sa.column("label_internal", sa.Text),
        sa.column("label_weclapp", sa.Text),
        sa.column("weclapp_column", sa.Text),
        sa.column("description", sa.Text),
        sa.column("scope", sa.Text),
        sa.column("max_length", sa.Integer),
        sa.column("is_mandatory", sa.Boolean),
        sa.column("write_policy", sa.Text),
        sa.column("edit_policy", sa.Text),
        sa.column("default_visible", sa.Boolean),
        sa.column("phase", sa.Integer),
        sa.column("note", sa.Text),
    )
    op.bulk_insert(field_alias, field_alias_seed_rows())

    op.alter_column("field_alias", "scope", nullable=False)
    op.alter_column("field_alias", "write_policy", nullable=False)
    op.alter_column("field_alias", "edit_policy", nullable=False)

    op.create_check_constraint(
        "ck_field_alias_scope",
        "field_alias",
        "scope IN ('supply_source', 'article', 'derived', 'context')",
    )
    op.create_check_constraint(
        "ck_field_alias_write_policy",
        "field_alias",
        "write_policy IN ('always', 'on_value', 'locked')",
    )
    op.create_check_constraint(
        "ck_field_alias_edit_policy",
        "field_alias",
        "edit_policy IN ('editable', 'read_only', 'derived')",
    )
    op.create_check_constraint(
        "ck_field_alias_phase",
        "field_alias",
        "phase IN (1, 2)",
    )

    op.add_column(
        "export_row",
        sa.Column(
            "extras",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "export_row",
        sa.Column(
            "article_context",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "export_row",
        sa.Column(
            "dropshipping_possible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "export_row",
        sa.Column(
            "weclapp_current_dropshipping",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "user_preference",
        sa.Column("user_oid", sa.Text(), primary_key=True, nullable=False),
        sa.Column("tool_key", sa.Text(), primary_key=True, nullable=False),
        sa.Column(
            "pref_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_preference")
    op.drop_column("export_row", "weclapp_current_dropshipping")
    op.drop_column("export_row", "dropshipping_possible")
    op.drop_column("export_row", "article_context")
    op.drop_column("export_row", "extras")
    op.drop_constraint("ck_field_alias_phase", "field_alias", type_="check")
    op.drop_constraint("ck_field_alias_edit_policy", "field_alias", type_="check")
    op.drop_constraint("ck_field_alias_write_policy", "field_alias", type_="check")
    op.drop_constraint("ck_field_alias_scope", "field_alias", type_="check")
    op.drop_column("field_alias", "note")
    op.drop_column("field_alias", "phase")
    op.drop_column("field_alias", "default_visible")
    op.drop_column("field_alias", "edit_policy")
    op.drop_column("field_alias", "write_policy")
    op.drop_column("field_alias", "is_mandatory")
    op.drop_column("field_alias", "max_length")
    op.drop_column("field_alias", "scope")
