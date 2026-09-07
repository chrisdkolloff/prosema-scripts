"""Keep priceless upload rows instead of skipping them.

Revision ID: 036_listenpreis_raw
Revises: 035_currency_overwritten
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "036_listenpreis_raw"
down_revision: Union[str, Sequence[str], None] = "035_currency_overwritten"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "supply_source_row",
        sa.Column("listenpreis_raw", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supply_source_row", "listenpreis_raw")
