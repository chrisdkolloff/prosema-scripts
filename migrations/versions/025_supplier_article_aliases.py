"""Supplier article number ↔ PROSEMA article aliases.

Revision ID: 025_supplier_article_aliases
Revises: 024_supplier_discount_categories

UNIQUE includes article_number on purpose: one supplier part number maps to
two PROSEMA articles in live data (four shared supply-source cases). A 1:1
on (supplier_id, supplier_article_number) would drop one of them.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025_supplier_article_aliases"
down_revision: Union[str, Sequence[str], None] = "024_supplier_discount_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supplier_article_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("supplier_article_number", sa.Text(), nullable=False),
        sa.Column("article_number", sa.Text(), nullable=False),
        sa.Column("weclapp_article_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confirmed_by", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_supplier_article_aliases_supplier_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "source IN ('supply_source', 'manual', 'ean', 'import')",
            name="ck_supplier_article_aliases_source",
        ),
        sa.UniqueConstraint(
            "supplier_id",
            "supplier_article_number",
            "article_number",
            name="uq_supplier_article_aliases_triple",
        ),
    )


def downgrade() -> None:
    op.drop_table("supplier_article_aliases")
