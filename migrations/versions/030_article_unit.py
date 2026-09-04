"""Article unit_id on the mirror, row unit, and weclapp_units catalogue.

Revision ID: 030_article_unit
Revises: 029_supply_source_apply

Currency stays an in-memory map during index. Units are persisted because the
preview grid needs the catalogue without a live weclapp call.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030_article_unit"
down_revision: Union[str, Sequence[str], None] = "029_supply_source_apply"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("weclapp_articles", sa.Column("unit_id", sa.Text(), nullable=True))
    op.add_column("supply_source_row", sa.Column("unit_id", sa.Text(), nullable=True))
    op.create_table(
        "weclapp_units",
        sa.Column("weclapp_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("weclapp_units")
    op.drop_column("supply_source_row", "unit_id")
    op.drop_column("weclapp_articles", "unit_id")
