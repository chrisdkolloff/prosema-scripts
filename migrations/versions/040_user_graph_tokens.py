"""Per-user Microsoft Graph refresh tokens (SharePoint / OneDrive read).

Revision ID: 040_user_graph_tokens
Revises: 039_user_shopify_tokens
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "040_user_graph_tokens"
down_revision: Union[str, Sequence[str], None] = "039_user_shopify_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_graph_tokens",
        sa.Column("oid", sa.Text(), primary_key=True, nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_graph_tokens")
