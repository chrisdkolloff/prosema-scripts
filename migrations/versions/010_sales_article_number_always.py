"""Verkaufsartikel-Nummer (W) always written from the PROSEMA article number.

Revision ID: 010_sales_article_number_always
Revises: 009_export_run_import_settings
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.supply_export_fields import field_alias_seed_rows

revision: str = "010_sales_article_number_always"
down_revision: Union[str, Sequence[str], None] = "009_export_run_import_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE field_alias
            SET write_policy = 'locked',
                edit_policy = 'read_only',
                phase = 2,
                is_mandatory = false,
                scope = 'article',
                note = 'nur bei Neuanlage',
                description = ''
            WHERE field_key = 'sales_article_number'
            """
        )
    )
