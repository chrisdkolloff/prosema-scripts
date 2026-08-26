"""Run-level import settings: Preis-Eintritt and Verkaufsartikel-Währung.

Revision ID: 009_export_run_import_settings
Revises: 008_export_column_model
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_export_run_import_settings"
down_revision: Union[str, Sequence[str], None] = "008_export_column_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "export_run",
        sa.Column(
            "sales_article_currency",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("export_run", "sales_article_currency")
