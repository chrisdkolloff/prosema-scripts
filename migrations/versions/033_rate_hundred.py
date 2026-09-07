"""Allow 100 % discount (stored fraction 1.0000).

Revision ID: 033_rate_hundred
Revises: 032_row_per_link

No value rewrite. The previous CHECK was ``rabatt_* < 1``, which blocked a
valid percent input of 100 (EK = 0).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "033_rate_hundred"
down_revision: Union[str, Sequence[str], None] = "032_row_per_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_supply_source_row_rabatt_1", "supply_source_row", type_="check"
    )
    op.drop_constraint(
        "ck_supply_source_row_rabatt_2", "supply_source_row", type_="check"
    )
    op.create_check_constraint(
        "ck_supply_source_row_rabatt_1",
        "supply_source_row",
        "rabatt_1 IS NULL OR (rabatt_1 >= 0 AND rabatt_1 <= 1)",
    )
    op.create_check_constraint(
        "ck_supply_source_row_rabatt_2",
        "supply_source_row",
        "rabatt_2 IS NULL OR (rabatt_2 >= 0 AND rabatt_2 <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_supply_source_row_rabatt_1", "supply_source_row", type_="check"
    )
    op.drop_constraint(
        "ck_supply_source_row_rabatt_2", "supply_source_row", type_="check"
    )
    op.create_check_constraint(
        "ck_supply_source_row_rabatt_1",
        "supply_source_row",
        "rabatt_1 IS NULL OR (rabatt_1 >= 0 AND rabatt_1 < 1)",
    )
    op.create_check_constraint(
        "ck_supply_source_row_rabatt_2",
        "supply_source_row",
        "rabatt_2 IS NULL OR (rabatt_2 >= 0 AND rabatt_2 < 1)",
    )
