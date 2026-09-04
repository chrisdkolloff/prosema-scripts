"""Allow DECLINED transform row_status.

Revision ID: 022_transform_declined
Revises: 021_transform_apply_unknown
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "022_transform_declined"
down_revision: Union[str, Sequence[str], None] = "021_transform_apply_unknown"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_transform_rows_status", "transform_rows", type_="check")
    op.create_check_constraint(
        "ck_transform_rows_status",
        "transform_rows",
        "row_status IN ('CHANGED', 'UNCHANGED', 'REFUSED', 'GONE', 'DECLINED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_transform_rows_status", "transform_rows", type_="check")
    op.create_check_constraint(
        "ck_transform_rows_status",
        "transform_rows",
        "row_status IN ('CHANGED', 'UNCHANGED', 'REFUSED', 'GONE')",
    )
