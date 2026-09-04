"""Allow UNKNOWN apply_outcome after a PUT with no audit row.

Revision ID: 021_transform_apply_unknown
Revises: 020_transform_word_position
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "021_transform_apply_unknown"
down_revision: Union[str, Sequence[str], None] = "020_transform_word_position"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_transform_rows_apply_outcome",
        "transform_rows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_transform_rows_apply_outcome",
        "transform_rows",
        "apply_outcome IS NULL OR apply_outcome IN ("
        "'UPDATED','UNCHANGED','CONFLICT','REJECTED','GONE',"
        "'REFUSED','UNAVAILABLE','UNKNOWN'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_transform_rows_apply_outcome",
        "transform_rows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_transform_rows_apply_outcome",
        "transform_rows",
        "apply_outcome IS NULL OR apply_outcome IN ("
        "'UPDATED','UNCHANGED','CONFLICT','REJECTED','GONE',"
        "'REFUSED','UNAVAILABLE'"
        ")",
    )
