"""Pin assistant results as an article-number selection.

Revision ID: 017_assistant_query_selection
Revises: 016_assistant_no_answer
Create Date: 2026-08-31

The Artikel-Übersicht cannot express a QueryFilter in its URL. Persist the
result instead: article numbers identify the same rows on a snapshot, and the
validated filter is stored only for provenance.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_assistant_query_selection"
down_revision: Union[str, Sequence[str], None] = "016_assistant_no_answer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assistant_queries",
        sa.Column("applied_article_numbers", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "assistant_queries",
        sa.Column("applied_filter", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "assistant_queries",
        sa.Column(
            "selection_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("assistant_queries", "selection_truncated")
    op.drop_column("assistant_queries", "applied_filter")
    op.drop_column("assistant_queries", "applied_article_numbers")
