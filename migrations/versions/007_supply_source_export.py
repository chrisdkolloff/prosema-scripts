"""Bezugsquellen-Export: field aliases, discount registry, export runs.

Revision ID: 007_supply_source_export
Revises: 006_article_snapshots
Create Date: 2026-08-25

discount_category rows are append-only: UPDATE is blocked by a trigger.
Rate changes close the old row (valid_to) and insert a new one.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_supply_source_export"
down_revision: Union[str, Sequence[str], None] = "006_article_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RABATTE_CSV = _REPO_ROOT / "data" / "produktgruppen_rabatte.csv"

DURAL_SUPPLIER_ID = "10000"
DURAL_SOURCE = "Dural Preisliste 2026-08"
DURAL_VALID_FROM = date(2026, 8, 1)
DURAL_RECORDED_BY = "migration:007_supply_source_export"

FIELD_ALIASES: tuple[dict[str, str], ...] = (
    {
        "field_key": "article_number",
        "label_internal": "Prosema Artikelnummer",
        "label_weclapp": "Verkaufsartikel-Nummer",
        "weclapp_column": "W",
        "description": "Prosema article number, internal key",
    },
    {
        "field_key": "supplier_article_number",
        "label_internal": "Lieferantenartikelnummer",
        "label_weclapp": "Lieferantenartikelnummer",
        "weclapp_column": "D",
        "description": "Article number at the supplier",
    },
    {
        "field_key": "supplier_number",
        "label_internal": "Lieferantennummer",
        "label_weclapp": "LIEFERANTENNUMMER",
        "weclapp_column": "F",
        "description": "Supplier ID in weclapp",
    },
    {
        "field_key": "article_name",
        "label_internal": "Artikelname",
        "label_weclapp": "ARTIKELNAME",
        "weclapp_column": "A",
        "description": "Short text",
    },
    {
        "field_key": "ek_price_before_discount_eur",
        "label_internal": "EK vor Rabatt (EUR)",
        "label_weclapp": "Bruttokaufpreis",
        "weclapp_column": "G",
        "description": "Net purchase price before discount (EUR)",
    },
    {
        "field_key": "unit",
        "label_internal": "Mengeneinheit",
        "label_weclapp": "Artikel-Mengeneinheit",
        "weclapp_column": "O",
        "description": "Base unit",
    },
    {
        "field_key": "discount_category",
        "label_internal": "Rabattkategorie",
        "label_weclapp": "",
        "weclapp_column": "",
        "description": "Supplier discount category code",
    },
    {
        "field_key": "matchcode",
        "label_internal": "Matchcode",
        "label_weclapp": "Matchcode",
        "weclapp_column": "P",
        "description": "Matchcode / reference",
    },
)


def _parse_percent(raw: str) -> Decimal:
    text = (raw or "").strip().replace("%", "").replace(",", ".")
    if not text or text in {"–", "-", "—"}:
        return Decimal("0")
    return Decimal(text).quantize(Decimal("0.01"))


def upgrade() -> None:
    op.create_table(
        "field_alias",
        sa.Column("field_key", sa.Text(), primary_key=True, nullable=False),
        sa.Column("label_internal", sa.Text(), nullable=False),
        sa.Column("label_weclapp", sa.Text(), nullable=False, server_default=""),
        sa.Column("weclapp_column", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "discount_category",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Text(), nullable=False),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("base_discount_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("customer_discount_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("recorded_by", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "supplier_id",
            "category_code",
            "valid_from",
            name="uq_discount_category_supplier_code_from",
        ),
    )
    op.create_index(
        "ix_discount_category_supplier_code_current",
        "discount_category",
        ["supplier_id", "category_code"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # Closing a rate sets valid_to (NULL → date). All other columns immutable.
    op.execute(
        """
        CREATE FUNCTION discount_category_before_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.supplier_id IS DISTINCT FROM OLD.supplier_id
               OR NEW.category_code IS DISTINCT FROM OLD.category_code
               OR NEW.label IS DISTINCT FROM OLD.label
               OR NEW.base_discount_pct IS DISTINCT FROM OLD.base_discount_pct
               OR NEW.customer_discount_pct IS DISTINCT FROM OLD.customer_discount_pct
               OR NEW.source IS DISTINCT FROM OLD.source
               OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
               OR NEW.recorded_by IS DISTINCT FROM OLD.recorded_by
               OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at THEN
                RAISE EXCEPTION
                    'discount_category is append-only; only valid_to may change (NULL → date)';
            END IF;
            IF OLD.valid_to IS NOT NULL THEN
                RAISE EXCEPTION 'discount_category row is already closed';
            END IF;
            IF NEW.valid_to IS NULL THEN
                RAISE EXCEPTION 'discount_category valid_to cannot be cleared';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_discount_category_before_update
        BEFORE UPDATE ON discount_category
        FOR EACH ROW
        EXECUTE FUNCTION discount_category_before_update();
        """
    )

    op.create_table(
        "export_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_oid", sa.Text(), nullable=False),
        sa.Column("created_by_name", sa.Text(), nullable=False),
        sa.Column("supplier_id", sa.Text(), nullable=False),
        sa.Column(
            "filter_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("file", sa.LargeBinary(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("included_count", sa.Integer(), nullable=True),
        sa.Column("price_entry_date", sa.Date(), nullable=True),
        sa.Column(
            "markup_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="50",
        ),
        sa.Column(
            "eur_chf_rate",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="0.9300",
        ),
        sa.Column("eur_chf_rate_date", sa.Date(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "summary_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('running', 'draft', 'exported', 'failed')",
            name="ck_export_run_status",
        ),
    )
    op.create_index(
        "ix_export_run_supplier_created",
        "export_run",
        ["supplier_id", "created_at"],
    )

    op.create_table(
        "export_row",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("article_number", sa.Text(), nullable=False, server_default=""),
        sa.Column("supplier_article_number", sa.Text(), nullable=False, server_default=""),
        sa.Column("supplier_number", sa.Text(), nullable=False, server_default=""),
        sa.Column("article_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("ek_price_before_discount", sa.Numeric(12, 2), nullable=True),
        sa.Column("unit", sa.Text(), nullable=False, server_default=""),
        sa.Column("matchcode", sa.Text(), nullable=False, server_default=""),
        sa.Column("discount_category", sa.Text(), nullable=False, server_default=""),
        sa.Column("discount_category_id", sa.Integer(), nullable=True),
        sa.Column("base_discount_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column(
            "customer_discount_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "discount_intent",
            sa.Text(),
            nullable=False,
            server_default="unresolved",
        ),
        sa.Column(
            "row_intent",
            sa.Text(),
            nullable=False,
            server_default="update",
        ),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column(
            "included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("weclapp_supply_source_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("weclapp_current_ek", sa.Numeric(12, 2), nullable=True),
        sa.Column("weclapp_current_base_discount_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "weclapp_current_customer_discount_pct",
            sa.Numeric(5, 2),
            nullable=True,
        ),
        sa.Column(
            "weclapp_current_is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("hauptgruppe_code", sa.Text(), nullable=False, server_default=""),
        sa.Column("untergruppe_code", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["export_run.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["discount_category_id"],
            ["discount_category.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "discount_intent IN ('apply', 'zero', 'unresolved')",
            name="ck_export_row_discount_intent",
        ),
        sa.CheckConstraint(
            "row_intent IN ('update', 'create')",
            name="ck_export_row_row_intent",
        ),
        sa.UniqueConstraint(
            "run_id",
            "article_number",
            "supplier_article_number",
            name="uq_export_row_run_article_supplier_article",
        ),
    )
    op.create_index("ix_export_row_run_position", "export_row", ["run_id", "position"])
    op.create_index(
        "ix_export_row_run_included",
        "export_row",
        ["run_id", "included"],
    )
    op.create_index(
        "ix_export_row_run_discount_category",
        "export_row",
        ["run_id", "discount_category"],
    )

    # Seeds
    field_alias = sa.table(
        "field_alias",
        sa.column("field_key", sa.Text),
        sa.column("label_internal", sa.Text),
        sa.column("label_weclapp", sa.Text),
        sa.column("weclapp_column", sa.Text),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(field_alias, list(FIELD_ALIASES))

    if _RABATTE_CSV.is_file():
        discount_rows: list[dict] = []
        with _RABATTE_CSV.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                code = (row.get("Kategorie") or "").strip()
                if not code:
                    continue
                discount_rows.append(
                    {
                        "supplier_id": DURAL_SUPPLIER_ID,
                        "category_code": code,
                        "label": (row.get("Produktgruppe") or "").strip() or None,
                        "base_discount_pct": _parse_percent(row.get("Grundrabatt") or ""),
                        "customer_discount_pct": _parse_percent(
                            row.get("Kundenrabatt") or ""
                        ),
                        "source": DURAL_SOURCE,
                        "valid_from": DURAL_VALID_FROM,
                        "valid_to": None,
                        "recorded_by": DURAL_RECORDED_BY,
                    }
                )
        if discount_rows:
            discount_category = sa.table(
                "discount_category",
                sa.column("supplier_id", sa.Text),
                sa.column("category_code", sa.Text),
                sa.column("label", sa.Text),
                sa.column("base_discount_pct", sa.Numeric),
                sa.column("customer_discount_pct", sa.Numeric),
                sa.column("source", sa.Text),
                sa.column("valid_from", sa.Date),
                sa.column("valid_to", sa.Date),
                sa.column("recorded_by", sa.Text),
            )
            op.bulk_insert(discount_category, discount_rows)


def downgrade() -> None:
    op.drop_table("export_row")
    op.drop_table("export_run")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_discount_category_before_update ON discount_category;"
    )
    op.execute("DROP FUNCTION IF EXISTS discount_category_before_update();")
    op.drop_table("discount_category")
    op.drop_table("field_alias")
