"""Per-supplier discount categories; migrate Dural CSV.

Revision ID: 024_supplier_discount_categories
Revises: 023_suppliers

Effective rate is not stored: derive as 1 − (1−r1)(1−r2).
Rates are fractions (0.50 = 50%), CHECK >= 0 AND < 1.
A bad CSV rate fails this migration; nothing is coerced.
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "024_supplier_discount_categories"
down_revision: Union[str, Sequence[str], None] = "023_suppliers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RABATTE_CSV = _REPO_ROOT / "data" / "produktgruppen_rabatte.csv"


def _parse_rate(raw: str, *, field: str, code: str) -> Decimal:
    original = (raw or "").strip()
    if not original:
        raise ValueError(
            f"Empty {field} for Kategorie {code!r} in {_RABATTE_CSV.name}"
        )
    had_percent = "%" in original
    text = original.replace("%", "").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"Unparseable {field} {original!r} for Kategorie {code!r}"
        ) from exc
    if had_percent:
        value = value / Decimal(100)
    if value < 0 or value >= 1:
        raise ValueError(
            f"{field} for Kategorie {code!r} is {original!r} → {value} "
            "(CHECK requires >= 0 AND < 1; not coercing)"
        )
    return value


def upgrade() -> None:
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

    if not _RABATTE_CSV.is_file():
        raise FileNotFoundError(
            f"Cannot seed supplier_discount_categories: {_RABATTE_CSV} missing"
        )

    conn = op.get_bind()
    dural_id = conn.execute(
        sa.text("SELECT id FROM suppliers WHERE supplier_number = '10000'")
    ).scalar_one()

    rows: list[dict] = []
    with _RABATTE_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            code = (raw.get("Kategorie") or "").strip()
            if not code:
                continue
            rows.append(
                {
                    "supplier_id": dural_id,
                    "code": code,
                    "label": (raw.get("Produktgruppe") or "").strip() or code,
                    "rabatt_1": _parse_rate(
                        raw.get("Grundrabatt") or "", field="Grundrabatt", code=code
                    ),
                    "rabatt_2": _parse_rate(
                        raw.get("Kundenrabatt") or "", field="Kundenrabatt", code=code
                    ),
                }
            )

    table = sa.table(
        "supplier_discount_categories",
        sa.column("supplier_id", sa.Integer),
        sa.column("code", sa.Text),
        sa.column("label", sa.Text),
        sa.column("rabatt_1", sa.Numeric),
        sa.column("rabatt_2", sa.Numeric),
    )
    op.bulk_insert(table, rows)


def downgrade() -> None:
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
