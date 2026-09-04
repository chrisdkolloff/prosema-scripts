"""Word-position flags for transform preview.

Revision ID: 020_transform_word_position
Revises: 019_transform_apply
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020_transform_word_position"
down_revision: Union[str, Sequence[str], None] = "019_transform_apply"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transform_runs",
        sa.Column(
            "word_positions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "transform_rows",
        sa.Column("inside_compound", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transform_rows", "inside_compound")
    op.drop_column("transform_runs", "word_positions")
