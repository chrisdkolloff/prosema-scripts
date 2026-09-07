"""Informational currency mismatch flag on supply_source_row.

Revision ID: 035_currency_overwritten
Revises: 034_supply_source_unit_raw

When run.einkaufswaehrung resolves to a different weclapp currencyId than the
current live price line, the write still uses the run currency; the row is
flagged like unit_overwritten.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035_currency_overwritten"
down_revision: Union[str, Sequence[str], None] = "034_supply_source_unit_raw"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "supply_source_row",
        sa.Column("live_currency_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column("resolved_currency_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "supply_source_row",
        sa.Column(
            "currency_overwritten",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("supply_source_row", "currency_overwritten")
    op.drop_column("supply_source_row", "resolved_currency_id")
    op.drop_column("supply_source_row", "live_currency_id")
