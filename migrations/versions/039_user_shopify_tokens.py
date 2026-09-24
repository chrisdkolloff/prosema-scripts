"""Per-user encrypted Shopify Admin API tokens.

Revision ID: 039_user_shopify_tokens
Revises: 038_retired_article_numbers
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "039_user_shopify_tokens"
down_revision: Union[str, Sequence[str], None] = "038_retired_article_numbers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_shopify_tokens",
        sa.Column("oid", sa.Text(), primary_key=True, nullable=False),
        sa.Column("token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_verified_ok", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_shopify_tokens")
