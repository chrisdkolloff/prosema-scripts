"""Allow locked_by_backfill on gruppen_audit.

Revision ID: 003_audit_locked_by_backfill
Revises: 002_create_gruppen
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003_audit_locked_by_backfill"
down_revision: Union[str, Sequence[str], None] = "002_create_gruppen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = (
    "action IN ("
    "'created', 'renamed', 'deleted', 'restored', "
    "'alias_added', 'alias_removed', 'locked_by_backfill'"
    ")"
)
_OLD = (
    "action IN ("
    "'created', 'renamed', 'deleted', 'restored', "
    "'alias_added', 'alias_removed'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_gruppen_audit_action", "gruppen_audit", type_="check")
    op.create_check_constraint("ck_gruppen_audit_action", "gruppen_audit", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_gruppen_audit_action", "gruppen_audit", type_="check")
    op.create_check_constraint("ck_gruppen_audit_action", "gruppen_audit", _OLD)
