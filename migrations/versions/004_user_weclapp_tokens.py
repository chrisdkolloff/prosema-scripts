"""Per-user encrypted weclapp API tokens.

Revision ID: 004_user_weclapp_tokens
Revises: 003_audit_locked_by_backfill
Create Date: 2026-08-24

Holds one credential per Entra oid. Not a users table: no names, roles,
or profile columns.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_user_weclapp_tokens"
down_revision: Union[str, Sequence[str], None] = "003_audit_locked_by_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_weclapp_tokens",
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
    op.drop_table("user_weclapp_tokens")
