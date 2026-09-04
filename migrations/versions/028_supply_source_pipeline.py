"""Supply-source resolve pipeline tables (sibling to frozen export_run).

Revision ID: 028_supply_source_pipeline
Revises: 027_drop_discount_register

Settings (einkaufswaehrung, kurs, verkaufswaehrung, aufschlag, preis_eintritt)
are snapshotted from suppliers at run creation, then edited on the run only.
They are never re-read from suppliers afterwards — a reopened run must
reproduce its original numbers even if the supplier default changed.

aufschlag is a MARKUP fraction (0.50 → × 1.50), unlike export_run.markup_pct
which is percent points (50 → × 1.50). The two tables sit next to each other;
do not copy values across.

Unique key on supply_source_row is (run_id, supplier_article_number). One row
may carry several PROSEMA article numbers. That is the opposite of
uq_export_row_run_article_supplier_article.

The running lock is independent of uq_export_run_supplier_running.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "028_supply_source_pipeline"
down_revision: Union[str, Sequence[str], None] = "027_drop_discount_register"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supply_source_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default="pull",
        ),
        sa.Column("datenstand", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("einkaufswaehrung", sa.Text(), nullable=False),
        sa.Column("kurs", sa.Numeric(10, 6), nullable=False),
        sa.Column("verkaufswaehrung", sa.Text(), nullable=False),
        sa.Column(
            "aufschlag",
            sa.Numeric(6, 4),
            nullable=False,
            comment=(
                "MARKUP fraction snapshotted from suppliers.default_aufschlag. "
                "0.50 means sale = EK × 1.50. Not export_run.markup_pct (percent points)."
            ),
        ),
        sa.Column(
            "preis_eintritt",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Maps to weclapp articlePrices[].startDate (epoch ms).",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_by_name", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_supply_source_run_supplier_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_supply_source_run_job_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('running','preview','approved','applying','applied','failed')",
            name="ck_supply_source_run_status",
        ),
        sa.CheckConstraint(
            "source IN ('pull','upload')",
            name="ck_supply_source_run_source",
        ),
        sa.CheckConstraint(
            "einkaufswaehrung IN ('EUR','CHF')",
            name="ck_supply_source_run_einkaufswaehrung",
        ),
        sa.CheckConstraint(
            "verkaufswaehrung IN ('EUR','CHF')",
            name="ck_supply_source_run_verkaufswaehrung",
        ),
        sa.CheckConstraint("kurs > 0", name="ck_supply_source_run_kurs_positive"),
        sa.CheckConstraint(
            "aufschlag >= 0",
            name="ck_supply_source_run_aufschlag_nonnegative",
        ),
        sa.CheckConstraint(
            "einkaufswaehrung <> 'CHF' OR kurs = 1.0",
            name="ck_supply_source_run_chf_kurs_unity",
        ),
    )
    op.create_index(
        "ix_supply_source_run_supplier_created",
        "supply_source_run",
        ["supplier_id", "created_at"],
    )
    op.create_index(
        "uq_supply_source_run_supplier_busy",
        "supply_source_run",
        ["supplier_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('running','applying')"),
    )
    op.execute(
        """
        COMMENT ON COLUMN supply_source_run.aufschlag IS
        'MARKUP fraction snapshotted from suppliers at run creation, then edited '
        'on the run only — never re-read from suppliers. 0.50 → × 1.50. '
        'Unlike export_run.markup_pct which stores percent points (50).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN supply_source_run.kurs IS
        'Snapshotted from suppliers.default_kurs at run creation; not re-read later.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN supply_source_run.einkaufswaehrung IS
        'Snapshotted from suppliers.einkaufswaehrung at run creation; not re-read later.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN supply_source_run.verkaufswaehrung IS
        'Snapshotted from suppliers.default_verkaufswaehrung at run creation; not re-read later.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN supply_source_run.preis_eintritt IS
        'Snapshotted/editable on the run. timestamptz for weclapp articlePrices.startDate.';
        """
    )

    op.create_table(
        "supply_source_row",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("supplier_article_number", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("ean", sa.Text(), nullable=True),
        sa.Column("listenpreis", sa.Numeric(14, 4), nullable=True),
        sa.Column("rabatt_1", sa.Numeric(6, 4), nullable=True),
        sa.Column("rabatt_2", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "discount_set",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("discount_source", sa.Text(), nullable=True),
        sa.Column(
            "rabattcode",
            sa.Text(),
            nullable=True,
            comment="Grouping key only. Never used to look up a rate.",
        ),
        sa.Column("match_tier", sa.Integer(), nullable=True),
        sa.Column(
            "match_status",
            sa.Text(),
            nullable=False,
            server_default="unmatched",
        ),
        sa.Column("row_intent", sa.Text(), nullable=True),
        sa.Column(
            "resolved_article_numbers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "weclapp_article_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("weclapp_supply_source_id", sa.Text(), nullable=True),
        sa.Column("weclapp_version", sa.Text(), nullable=True),
        sa.Column("current_ek", sa.Numeric(14, 4), nullable=True),
        sa.Column("current_ek_currency", sa.Text(), nullable=True),
        sa.Column("vk_override", sa.Numeric(14, 4), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["supply_source_run.id"],
            name="fk_supply_source_row_run_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "rabatt_1 IS NULL OR (rabatt_1 >= 0 AND rabatt_1 < 1)",
            name="ck_supply_source_row_rabatt_1",
        ),
        sa.CheckConstraint(
            "rabatt_2 IS NULL OR (rabatt_2 >= 0 AND rabatt_2 < 1)",
            name="ck_supply_source_row_rabatt_2",
        ),
        sa.CheckConstraint(
            "discount_source IS NULL OR discount_source IN ('manual','carried')",
            name="ck_supply_source_row_discount_source",
        ),
        sa.CheckConstraint(
            "match_tier IS NULL OR (match_tier >= 1 AND match_tier <= 4)",
            name="ck_supply_source_row_match_tier",
        ),
        sa.CheckConstraint(
            "match_status IN ('matched','unmatched')",
            name="ck_supply_source_row_match_status",
        ),
        sa.CheckConstraint(
            "row_intent IS NULL OR row_intent IN "
            "('update','price_only','create','attach','renumber','skip')",
            name="ck_supply_source_row_row_intent",
        ),
        sa.UniqueConstraint(
            "run_id",
            "supplier_article_number",
            name="uq_supply_source_row_run_san",
        ),
    )
    op.create_index(
        "ix_supply_source_row_run_id",
        "supply_source_row",
        ["run_id"],
    )
    op.create_index(
        "ix_supply_source_row_run_rabattcode",
        "supply_source_row",
        ["run_id", "rabattcode"],
    )
    op.execute(
        """
        COMMENT ON COLUMN supply_source_row.rabattcode IS
        'Grouping key only (weclapp Rabattcode). Carries no rates.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN supply_source_row.discount_set IS
        'False means rates are blank, never treat as zero. Kein Rabatt writes 0/0 and true.';
        """
    )

    op.execute(
        """
        CREATE FUNCTION supply_source_run_set_updated_at()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_supply_source_run_set_updated_at
        BEFORE UPDATE ON supply_source_run
        FOR EACH ROW EXECUTE FUNCTION supply_source_run_set_updated_at();
        """
    )
    op.execute(
        """
        CREATE FUNCTION supply_source_row_set_updated_at()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_supply_source_row_set_updated_at
        BEFORE UPDATE ON supply_source_row
        FOR EACH ROW EXECUTE FUNCTION supply_source_row_set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_supply_source_row_set_updated_at "
        "ON supply_source_row;"
    )
    op.execute("DROP FUNCTION IF EXISTS supply_source_row_set_updated_at();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_supply_source_run_set_updated_at "
        "ON supply_source_run;"
    )
    op.execute("DROP FUNCTION IF EXISTS supply_source_run_set_updated_at();")
    op.drop_index("ix_supply_source_row_run_rabattcode", table_name="supply_source_row")
    op.drop_index("ix_supply_source_row_run_id", table_name="supply_source_row")
    op.drop_table("supply_source_row")
    op.drop_index("uq_supply_source_run_supplier_busy", table_name="supply_source_run")
    op.drop_index("ix_supply_source_run_supplier_created", table_name="supply_source_run")
    op.drop_table("supply_source_run")
