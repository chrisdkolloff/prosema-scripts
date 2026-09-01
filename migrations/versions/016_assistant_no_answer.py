"""Allow no_answer on assistant_queries.outcome.

Revision ID: 016_assistant_no_answer
Revises: 015_assistant_invalid_input
Create Date: 2026-08-31

Soft-failure when the turn budget or duplicate-call limit is hit after a
successful row-returning tool call: show the table instead of an error page.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "016_assistant_no_answer"
down_revision: Union[str, Sequence[str], None] = "015_assistant_invalid_input"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW = (
    "outcome IN ("
    "'answered','answered_unverified','no_result','no_answer',"
    "'refused','invalid_input','error','unavailable'"
    ")"
)
_OLD = (
    "outcome IN ("
    "'answered','answered_unverified','no_result',"
    "'refused','invalid_input','error','unavailable'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_assistant_queries_outcome", "assistant_queries", type_="check")
    op.create_check_constraint("ck_assistant_queries_outcome", "assistant_queries", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_assistant_queries_outcome", "assistant_queries", type_="check")
    op.create_check_constraint("ck_assistant_queries_outcome", "assistant_queries", _OLD)
