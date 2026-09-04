"""Local weclapp supply-source mirror (read-only) plus per-supplier export_run lock.

Revision ID: 026_weclapp_supply_source_mirror
Revises: 025_supplier_article_aliases

These tables are a rebuildable mirror. They are never the source of truth
and nothing writes to weclapp from them.

The previous export_run running lock was Python-only
(app.supply_exports.running_export looks at any status='running' row).
This revision adds a per-supplier unique index. The Python global check is
left in place because the Dural export files are frozen in this change.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "026_weclapp_supply_source_mirror"
down_revision: Union[str, Sequence[str], None] = "025_supplier_article_aliases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_export_run_supplier_running",
        "export_run",
        ["supplier_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "weclapp_articles",
        sa.Column("weclapp_article_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("article_number", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("ean", sa.Text(), nullable=True),
        sa.Column("rabattcode", sa.Text(), nullable=True),
        sa.Column("weclapp_version", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("missing_since", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_weclapp_articles_article_number",
        "weclapp_articles",
        ["article_number"],
    )
    op.create_index("ix_weclapp_articles_ean", "weclapp_articles", ["ean"])

    op.create_table(
        "weclapp_supply_sources",
        sa.Column("weclapp_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("supplier_party_id", sa.Text(), nullable=False),
        sa.Column("supplier_number", sa.Text(), nullable=False),
        sa.Column(
            "supplier_article_number",
            sa.Text(),
            nullable=False,
            comment="SS.articleNumber — the SUPPLIER's part number, not the PROSEMA article number.",
        ),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("unit_id", sa.Text(), nullable=True),
        sa.Column("tax_rate_type", sa.Text(), nullable=True),
        sa.Column("ean", sa.Text(), nullable=True),
        sa.Column("min_purchase_qty", sa.Numeric(), nullable=True),
        sa.Column("fixed_purchase_qty", sa.Numeric(), nullable=True),
        sa.Column("procurement_lead_days", sa.Integer(), nullable=True),
        sa.Column("weclapp_version", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("missing_since", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "supplier_party_id",
            "supplier_article_number",
            name="uq_weclapp_supply_sources_party_san",
        ),
    )

    op.create_table(
        "weclapp_supply_source_prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supply_source_weclapp_id", sa.Text(), nullable=False),
        sa.Column(
            "weclapp_price_id",
            sa.Text(),
            nullable=True,
            comment=(
                "Diff aid only. NOT a durable key — weclapp deletes and reissues nested "
                "price ids whenever the articlePrices array is replaced. Never use this "
                "to reconstruct a payload; always re-read live before writing."
            ),
        ),
        sa.Column("price", sa.Numeric(14, 4), nullable=True),
        sa.Column("currency_id", sa.Text(), nullable=True),
        sa.Column("currency_code", sa.Text(), nullable=True),
        sa.Column("start_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reduction_additions", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["supply_source_weclapp_id"],
            ["weclapp_supply_sources.weclapp_id"],
            name="fk_weclapp_ss_prices_ss",
            ondelete="CASCADE",
        ),
    )
    op.execute(
        """
        COMMENT ON COLUMN weclapp_supply_source_prices.weclapp_price_id IS
        'Diff aid only. NOT a durable key — weclapp deletes and reissues nested price '
        'ids whenever the articlePrices array is replaced. Never use this to reconstruct '
        'a payload; always re-read live before writing.';
        """
    )

    op.create_table(
        "weclapp_supply_source_links",
        sa.Column("supply_source_weclapp_id", sa.Text(), nullable=False),
        sa.Column("weclapp_article_id", sa.Text(), nullable=False),
        sa.Column("article_number", sa.Text(), nullable=False),
        sa.Column("supplier_party_id", sa.Text(), nullable=False),
        sa.Column("position_number", sa.Integer(), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.PrimaryKeyConstraint(
            "supply_source_weclapp_id",
            "weclapp_article_id",
            name="pk_weclapp_supply_source_links",
        ),
        sa.ForeignKeyConstraint(
            ["supply_source_weclapp_id"],
            ["weclapp_supply_sources.weclapp_id"],
            name="fk_weclapp_ss_links_ss",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "weclapp_article_id",
            "supplier_party_id",
            name="uq_weclapp_ss_links_article_supplier",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION weclapp_ss_links_party_from_parent()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_party text;
        BEGIN
            SELECT supplier_party_id INTO parent_party
            FROM weclapp_supply_sources
            WHERE weclapp_id = NEW.supply_source_weclapp_id;
            IF parent_party IS NULL THEN
                RAISE EXCEPTION
                    'weclapp_supply_source_links: parent supply source % missing',
                    NEW.supply_source_weclapp_id;
            END IF;
            NEW.supplier_party_id := parent_party;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weclapp_ss_links_party_from_parent
        BEFORE INSERT OR UPDATE OF supply_source_weclapp_id, supplier_party_id
        ON weclapp_supply_source_links
        FOR EACH ROW
        EXECUTE FUNCTION weclapp_ss_links_party_from_parent();
        """
    )
    op.execute(
        """
        CREATE FUNCTION weclapp_ss_cascade_party_to_links()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.supplier_party_id IS DISTINCT FROM OLD.supplier_party_id THEN
                UPDATE weclapp_supply_source_links
                SET supplier_party_id = NEW.supplier_party_id
                WHERE supply_source_weclapp_id = NEW.weclapp_id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weclapp_ss_cascade_party_to_links
        AFTER UPDATE OF supplier_party_id ON weclapp_supply_sources
        FOR EACH ROW
        EXECUTE FUNCTION weclapp_ss_cascade_party_to_links();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_weclapp_ss_cascade_party_to_links "
        "ON weclapp_supply_sources;"
    )
    op.execute("DROP FUNCTION IF EXISTS weclapp_ss_cascade_party_to_links();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_weclapp_ss_links_party_from_parent "
        "ON weclapp_supply_source_links;"
    )
    op.execute("DROP FUNCTION IF EXISTS weclapp_ss_links_party_from_parent();")
    op.drop_table("weclapp_supply_source_links")
    op.drop_table("weclapp_supply_source_prices")
    op.drop_table("weclapp_supply_sources")
    op.drop_index("ix_weclapp_articles_ean", table_name="weclapp_articles")
    op.drop_index("ix_weclapp_articles_article_number", table_name="weclapp_articles")
    op.drop_table("weclapp_articles")
    op.drop_index("uq_export_run_supplier_running", table_name="export_run")
