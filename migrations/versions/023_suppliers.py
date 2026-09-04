"""Suppliers table, audit, Dural/Lenzhard/Axpel/Juralith seed.

Revision ID: 023_suppliers
Revises: 022_transform_declined

IDs 011–014 are already taken in this repo (job leases, batch artefacts,
article templates, assistant queries). Production here is past 010;
this revision continues from current head 022.

default_aufschlag is a MARKUP, not a margin. 0.50 means sale = EK × 1.50.
Confusing markup with margin makes every price wrong by a third.

default_unit_id is nullable: unit resolution on the create path is still open.
einkaufswaehrung is a UI default, not an enforced weclapp truth (discovery B5).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "023_suppliers"
down_revision: Union[str, Sequence[str], None] = "022_transform_declined"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = (
    {
        "supplier_number": "10000",
        "weclapp_party_id": "4406",
        "name": "DURAL GmbH",
        "einkaufswaehrung": "EUR",
        "default_kurs": Decimal("0.93"),
        "default_aufschlag": Decimal("0.50"),
    },
    {
        "supplier_number": "10061",
        "weclapp_party_id": "197093",
        "name": "Hülsenfabrik Lenzhard",
        "einkaufswaehrung": "CHF",
        "default_kurs": Decimal("1.0"),
        "default_aufschlag": Decimal("0.50"),
    },
    {
        "supplier_number": "10739",
        "weclapp_party_id": "394644",
        "name": "Axpel one for all AG",
        "einkaufswaehrung": "CHF",
        "default_kurs": Decimal("1.0"),
        "default_aufschlag": Decimal("0.50"),
    },
    {
        "supplier_number": "10055",
        "weclapp_party_id": "178825",
        "name": "JURALITH Baustoff GmbH",
        "einkaufswaehrung": "EUR",
        "default_kurs": Decimal("0.93"),
        "default_aufschlag": Decimal("0.50"),
    },
)


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_number", sa.Text(), nullable=False),
        sa.Column("weclapp_party_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("einkaufswaehrung", sa.Text(), nullable=False),
        sa.Column("default_kurs", sa.Numeric(10, 6), nullable=False),
        sa.Column(
            "default_aufschlag",
            sa.Numeric(6, 4),
            nullable=False,
            comment=(
                "MARKUP, not margin. 0.50 reproduces today's × 1.50. "
                "A 50% margin would be 1.00 and would price every article a third too high."
            ),
        ),
        sa.Column(
            "default_verkaufswaehrung",
            sa.Text(),
            nullable=False,
            server_default="CHF",
        ),
        sa.Column(
            "default_unit_id",
            sa.Text(),
            nullable=True,
            comment="weclapp unitId; nullable until create-path unit resolution is decided.",
        ),
        sa.Column("template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("supplier_number", name="uq_suppliers_supplier_number"),
        sa.UniqueConstraint("weclapp_party_id", name="uq_suppliers_weclapp_party_id"),
        sa.ForeignKeyConstraint(
            ["template_version_id"],
            ["article_templates.id"],
            name="fk_suppliers_template_version_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "einkaufswaehrung IN ('EUR', 'CHF')",
            name="ck_suppliers_einkaufswaehrung",
        ),
        sa.CheckConstraint(
            "default_verkaufswaehrung IN ('EUR', 'CHF')",
            name="ck_suppliers_default_verkaufswaehrung",
        ),
        sa.CheckConstraint("default_kurs > 0", name="ck_suppliers_default_kurs_positive"),
        sa.CheckConstraint(
            "default_aufschlag >= 0",
            name="ck_suppliers_default_aufschlag_nonnegative",
        ),
        sa.CheckConstraint(
            "einkaufswaehrung <> 'CHF' OR default_kurs = 1.0",
            name="ck_suppliers_chf_kurs_unity",
        ),
    )

    # Same shape as gruppen_audit (id, entity, entity_id, action, before, after,
    # actor_oid, actor_name, at). entity_id is Integer because suppliers.id is serial,
    # not UUID.
    op.create_table(
        "suppliers_audit",
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
        sa.CheckConstraint("entity IN ('supplier')", name="ck_suppliers_audit_entity"),
        sa.CheckConstraint(
            "action IN ('created', 'renamed', 'updated', 'deleted', 'restored')",
            name="ck_suppliers_audit_action",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION suppliers_set_updated_at()
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
        CREATE TRIGGER trg_suppliers_set_updated_at
        BEFORE UPDATE ON suppliers
        FOR EACH ROW
        EXECUTE FUNCTION suppliers_set_updated_at();
        """
    )

    table = sa.table(
        "suppliers",
        sa.column("supplier_number", sa.Text),
        sa.column("weclapp_party_id", sa.Text),
        sa.column("name", sa.Text),
        sa.column("einkaufswaehrung", sa.Text),
        sa.column("default_kurs", sa.Numeric),
        sa.column("default_aufschlag", sa.Numeric),
    )
    op.bulk_insert(table, list(_SEED))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_suppliers_set_updated_at ON suppliers;")
    op.execute("DROP FUNCTION IF EXISTS suppliers_set_updated_at();")
    op.drop_table("suppliers_audit")
    op.drop_table("suppliers")
