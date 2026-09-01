"""Allow invalid_input on assistant_queries.outcome.

Revision ID: 015_assistant_invalid_input
Revises: 014_assistant_queries
Create Date: 2026-08-31

Splits empty-question scoring from a model refusal.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "015_assistant_invalid_input"
down_revision: Union[str, Sequence[str], None] = "014_assistant_queries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = (
    "outcome IN ("
    "'answered','answered_unverified','no_result',"
    "'refused','invalid_input','error','unavailable'"
    ")"
)
_OLD = (
    "outcome IN ("
    "'answered','answered_unverified','no_result',"
    "'refused','error','unavailable'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_assistant_queries_outcome", "assistant_queries", type_="check")
    op.create_check_constraint("ck_assistant_queries_outcome", "assistant_queries", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_assistant_queries_outcome", "assistant_queries", type_="check")
    op.create_check_constraint("ck_assistant_queries_outcome", "assistant_queries", _OLD)
