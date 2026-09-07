"""Persist supplier-file unit word on supply_source_row, and a per-supplier
alias from that word to a weclapp unitId.

Revision ID: 034_supply_source_unit_raw
Revises: 033_rate_hundred

POST /unit and suppliers.default_unit_id are out of scope.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034_supply_source_unit_raw"
down_revision: Union[str, Sequence[str], None] = "033_rate_hundred"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("supply_source_row", sa.Column("unit_raw", sa.Text(), nullable=True))
    # Same type as supply_source_row.unit_id (030_article_unit: sa.Text()).
    op.add_column("supply_source_row", sa.Column("file_unit_id", sa.Text(), nullable=True))
    op.add_column(
        "supply_source_row",
        sa.Column(
            "unit_overwritten",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "supplier_unit_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("supplier_word", sa.Text(), nullable=False),
        sa.Column("word_key", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_supplier_unit_aliases_supplier_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "supplier_id",
            "word_key",
            name="uq_supplier_unit_aliases_supplier_id_word_key",
        ),
    )
    op.create_index(
        "ix_supplier_unit_aliases_supplier_id",
        "supplier_unit_aliases",
        ["supplier_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_supplier_unit_aliases_supplier_id",
        table_name="supplier_unit_aliases",
    )
    op.drop_table("supplier_unit_aliases")
    op.drop_column("supply_source_row", "unit_overwritten")
    op.drop_column("supply_source_row", "file_unit_id")
    op.drop_column("supply_source_row", "unit_raw")
