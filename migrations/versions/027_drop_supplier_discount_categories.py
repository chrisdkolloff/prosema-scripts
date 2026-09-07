"""Drop unused supplier_discount_categories register (added in 024).

Revision ID: 027_drop_discount_register
Revises: 026_weclapp_supply_source_mirror

Rates are set per run on supply_source_row, not looked up from a register.
The 007 discount_category table used by the live Dural CSV export is untouched.

Downgrade recreates empty tables. The 8 seeded Dural rows from 024 are not
recoverable; data/produktgruppen_rabatte.csv remains in the repo.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027_drop_discount_register"
down_revision: Union[str, Sequence[str], None] = "026_weclapp_supply_source_mirror"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_supplier_discount_categories_set_updated_at "
        "ON supplier_discount_categories;"
    )
    op.execute("DROP FUNCTION IF EXISTS supplier_discount_categories_set_updated_at();")
    op.drop_table("supplier_discount_categories_audit")
    op.drop_index(
        "uq_supplier_discount_categories_supplier_code_live",
        table_name="supplier_discount_categories",
    )
    op.drop_table("supplier_discount_categories")


def downgrade() -> None:
    # Schema only. The 8 Dural rows seeded in 024 are not restored.
    op.create_table(
        "supplier_discount_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("rabatt_1", sa.Numeric(6, 4), nullable=False),
        sa.Column("rabatt_2", sa.Numeric(6, 4), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_supplier_discount_categories_supplier_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "rabatt_1 >= 0 AND rabatt_1 < 1",
            name="ck_supplier_discount_categories_rabatt_1",
        ),
        sa.CheckConstraint(
            "rabatt_2 >= 0 AND rabatt_2 < 1",
            name="ck_supplier_discount_categories_rabatt_2",
        ),
    )
    op.create_index(
        "uq_supplier_discount_categories_supplier_code_live",
        "supplier_discount_categories",
        ["supplier_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "supplier_discount_categories_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_oid", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.Text(), nullable=False),
        sa.Column(
            "at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "entity IN ('discount_category')",
            name="ck_supplier_discount_categories_audit_entity",
        ),
        sa.CheckConstraint(
            "action IN ('created', 'renamed', 'updated', 'deleted', 'restored')",
            name="ck_supplier_discount_categories_audit_action",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION supplier_discount_categories_set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_supplier_discount_categories_set_updated_at
        BEFORE UPDATE ON supplier_discount_categories
        FOR EACH ROW
        EXECUTE FUNCTION supplier_discount_categories_set_updated_at();
        """
    )
