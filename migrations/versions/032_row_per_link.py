"""Global supply-source template; one row per article link.

Revision ID: 032_row_per_link
Revises: 031_supply_source_upload

One Christopher preview upload exists (run 151, unmatched SAN, empty article
arrays). Convert in place; do not expand arrays. Drop unused
suppliers.template_version_id (FK to article_templates; nothing reads it).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "032_row_per_link"
down_revision: Union[str, Sequence[str], None] = "031_supply_source_upload"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_suppliers_template_version_id", "suppliers", type_="foreignkey")
    op.drop_column("suppliers", "template_version_id")

    op.execute(
        """
        DELETE FROM supply_source_templates t
        WHERE t.id NOT IN (
            SELECT DISTINCT template_id FROM supply_source_uploads
            UNION
            SELECT DISTINCT template_id FROM supply_source_run WHERE template_id IS NOT NULL
            UNION
            SELECT MIN(id) FROM supply_source_templates
        )
        """
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS ver
            FROM supply_source_templates
        )
        UPDATE supply_source_templates t
        SET version = numbered.ver,
            is_active = (numbered.ver = 1)
        FROM numbered
        WHERE t.id = numbered.id
        """
    )
    op.drop_index("uq_supply_source_templates_active", table_name="supply_source_templates")
    op.drop_constraint(
        "uq_supply_source_templates_supplier_version",
        "supply_source_templates",
        type_="unique",
    )
    op.drop_column("supply_source_templates", "supplier_id")
    op.create_unique_constraint(
        "uq_supply_source_templates_version",
        "supply_source_templates",
        ["version"],
    )
    op.create_index(
        "uq_supply_source_templates_active",
        "supply_source_templates",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.add_column("supply_source_row", sa.Column("article_number", sa.Text(), nullable=True))
    op.add_column(
        "supply_source_row", sa.Column("weclapp_article_id", sa.Text(), nullable=True)
    )
    op.add_column(
        "supply_source_row",
        sa.Column(
            "included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.execute(
        """
        UPDATE supply_source_row
        SET article_number = CASE
                WHEN cardinality(resolved_article_numbers) = 1
                THEN resolved_article_numbers[1]
                ELSE NULL
            END,
            weclapp_article_id = CASE
                WHEN cardinality(weclapp_article_ids) = 1
                THEN weclapp_article_ids[1]
                ELSE NULL
            END
        """
    )
    op.drop_constraint("uq_supply_source_row_run_san", "supply_source_row", type_="unique")
    op.drop_column("supply_source_row", "resolved_article_numbers")
    op.drop_column("supply_source_row", "weclapp_article_ids")
    op.create_unique_constraint(
        "uq_supply_source_row_run_san_article",
        "supply_source_row",
        ["run_id", "supplier_article_number", "article_number"],
    )
    op.create_index(
        "uq_supply_source_row_run_san_unmatched",
        "supply_source_row",
        ["run_id", "supplier_article_number"],
        unique=True,
        postgresql_where=sa.text("article_number IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_supply_source_row_run_san_unmatched", table_name="supply_source_row"
    )
    op.drop_constraint(
        "uq_supply_source_row_run_san_article", "supply_source_row", type_="unique"
    )
    op.add_column(
        "supply_source_row",
        sa.Column(
            "resolved_article_numbers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "supply_source_row",
        sa.Column(
            "weclapp_article_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.execute(
        """
        UPDATE supply_source_row
        SET resolved_article_numbers = CASE
                WHEN article_number IS NULL THEN '{}'::text[]
                ELSE ARRAY[article_number]
            END,
            weclapp_article_ids = CASE
                WHEN weclapp_article_id IS NULL THEN '{}'::text[]
                ELSE ARRAY[weclapp_article_id]
            END
        """
    )
    op.drop_column("supply_source_row", "included")
    op.drop_column("supply_source_row", "weclapp_article_id")
    op.drop_column("supply_source_row", "article_number")
    op.create_unique_constraint(
        "uq_supply_source_row_run_san",
        "supply_source_row",
        ["run_id", "supplier_article_number"],
    )

    op.drop_index("uq_supply_source_templates_active", table_name="supply_source_templates")
    op.drop_constraint(
        "uq_supply_source_templates_version",
        "supply_source_templates",
        type_="unique",
    )
    op.add_column(
        "supply_source_templates",
        sa.Column("supplier_id", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE supply_source_templates
        SET supplier_id = (SELECT MIN(id) FROM suppliers)
        WHERE supplier_id IS NULL
        """
    )
    op.alter_column("supply_source_templates", "supplier_id", nullable=False)
    op.create_foreign_key(
        "supply_source_templates_supplier_id_fkey",
        "supply_source_templates",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_supply_source_templates_supplier_version",
        "supply_source_templates",
        ["supplier_id", "version"],
    )
    op.create_index(
        "uq_supply_source_templates_active",
        "supply_source_templates",
        ["supplier_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.add_column(
        "suppliers",
        sa.Column("template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_suppliers_template_version_id",
        "suppliers",
        "article_templates",
        ["template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
