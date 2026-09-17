"""Retired Prosema article numbers (tombstones after admin renumber).

Revision ID: 038_retired_article_numbers
Revises: 037_lock_groups_on_create
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "038_retired_article_numbers"
down_revision: Union[str, Sequence[str], None] = "037_lock_groups_on_create"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retired_article_numbers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("weclapp_article_id", sa.Text(), nullable=False),
        sa.Column("retired_number", sa.Text(), nullable=False),
        sa.Column("new_number", sa.Text(), nullable=False),
        sa.Column("destination_haupt", sa.Text(), nullable=False),
        sa.Column("destination_unter", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_oid", sa.Text(), nullable=False),
        sa.Column("created_by_name", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_retired_article_numbers_retired_number",
        "retired_article_numbers",
        ["retired_number"],
    )
    op.create_index(
        "ix_retired_article_numbers_weclapp_article_id",
        "retired_article_numbers",
        ["weclapp_article_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retired_article_numbers_weclapp_article_id",
        table_name="retired_article_numbers",
    )
    op.drop_index(
        "ix_retired_article_numbers_retired_number",
        table_name="retired_article_numbers",
    )
    op.drop_table("retired_article_numbers")
