"""Backfill locked_at for groups created before lock-on-create.

Revision ID: 037_lock_groups_on_create
Revises: 036_listenpreis_raw
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "037_lock_groups_on_create"
down_revision: Union[str, Sequence[str], None] = "036_listenpreis_raw"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE hauptgruppen
        SET locked_at = created_at
        WHERE locked_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE untergruppen
        SET locked_at = created_at
        WHERE locked_at IS NULL
        """
    )


def downgrade() -> None:
    # Irreversible: cannot distinguish create-time locks from registration locks.
    pass
