"""Create group registry tables and protective triggers.

Revision ID: 002_create_gruppen
Revises: 001_create_jobs
Create Date: 2026-08-24

locked_at is set by article registration (week 3) the first time a number is
issued under that group pair. Nothing in week 2 writes this column.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_create_gruppen"
down_revision: Union[str, Sequence[str], None] = "001_create_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hauptgruppen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # locked_at is set by article registration (week 3) the first time a
        # number is issued under this group. Nothing in week 2 writes this column.
        sa.Column("locked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.CheckConstraint("code ~ '^[0-9]{3}$'", name="ck_hauptgruppen_code"),
    )
    op.create_index(
        "uq_hauptgruppen_code_active",
        "hauptgruppen",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "untergruppen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("hauptgruppe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # locked_at is set by article registration (week 3) the first time a
        # number is issued under this group. Nothing in week 2 writes this column.
        sa.Column("locked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            ["hauptgruppe_id"],
            ["hauptgruppen.id"],
            name="fk_untergruppen_hauptgruppe_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("code ~ '^[0-9]{3}$'", name="ck_untergruppen_code"),
    )
    op.create_index(
        "uq_untergruppen_parent_code_active",
        "untergruppen",
        ["hauptgruppe_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "gruppen_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("alias_normalized", sa.Text(), nullable=False),
        sa.Column("hauptgruppe_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("untergruppe_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["hauptgruppe_id"],
            ["hauptgruppen.id"],
            name="fk_gruppen_aliases_hauptgruppe_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["untergruppe_id"],
            ["untergruppen.id"],
            name="fk_gruppen_aliases_untergruppe_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(hauptgruppe_id IS NOT NULL AND untergruppe_id IS NULL)"
            " OR (hauptgruppe_id IS NULL AND untergruppe_id IS NOT NULL)",
            name="ck_gruppen_aliases_one_target",
        ),
    )
    op.create_index(
        "uq_gruppen_aliases_normalized_hauptgruppe",
        "gruppen_aliases",
        ["alias_normalized"],
        unique=True,
        postgresql_where=sa.text("hauptgruppe_id IS NOT NULL"),
    )
    op.create_index(
        "uq_gruppen_aliases_normalized_untergruppe",
        "gruppen_aliases",
        ["alias_normalized"],
        unique=True,
        postgresql_where=sa.text("untergruppe_id IS NOT NULL"),
    )

    op.create_table(
        "gruppen_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "entity IN ('hauptgruppe', 'untergruppe', 'alias')",
            name="ck_gruppen_audit_entity",
        ),
        sa.CheckConstraint(
            "action IN ("
            "'created', 'renamed', 'deleted', 'restored', "
            "'alias_added', 'alias_removed'"
            ")",
            name="ck_gruppen_audit_action",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION forbid_hard_delete_gruppen()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'hard delete of groups is forbidden; use soft delete';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_hauptgruppen_forbid_delete
        BEFORE DELETE ON hauptgruppen
        FOR EACH ROW
        EXECUTE FUNCTION forbid_hard_delete_gruppen();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_untergruppen_forbid_delete
        BEFORE DELETE ON untergruppen
        FOR EACH ROW
        EXECUTE FUNCTION forbid_hard_delete_gruppen();
        """
    )

    op.execute(
        """
        CREATE FUNCTION hauptgruppen_before_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.locked_at IS NOT NULL AND NEW.locked_at IS NULL THEN
                RAISE EXCEPTION 'locked_at cannot be cleared';
            END IF;
            IF OLD.locked_at IS NOT NULL AND NEW.code IS DISTINCT FROM OLD.code THEN
                RAISE EXCEPTION 'group code is locked and cannot be changed';
            END IF;
            IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
                IF EXISTS (
                    SELECT 1 FROM untergruppen
                    WHERE hauptgruppe_id = OLD.id AND deleted_at IS NULL
                ) THEN
                    RAISE EXCEPTION 'cannot soft-delete hauptgruppe with live untergruppen';
                END IF;
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_hauptgruppen_before_update
        BEFORE UPDATE ON hauptgruppen
        FOR EACH ROW
        EXECUTE FUNCTION hauptgruppen_before_update();
        """
    )

    op.execute(
        """
        CREATE FUNCTION untergruppen_before_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.locked_at IS NOT NULL AND NEW.locked_at IS NULL THEN
                RAISE EXCEPTION 'locked_at cannot be cleared';
            END IF;
            IF OLD.locked_at IS NOT NULL AND NEW.code IS DISTINCT FROM OLD.code THEN
                RAISE EXCEPTION 'group code is locked and cannot be changed';
            END IF;
            IF OLD.locked_at IS NOT NULL
               AND NEW.hauptgruppe_id IS DISTINCT FROM OLD.hauptgruppe_id THEN
                RAISE EXCEPTION 'group parent is locked and cannot be changed';
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_untergruppen_before_update
        BEFORE UPDATE ON untergruppen
        FOR EACH ROW
        EXECUTE FUNCTION untergruppen_before_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_untergruppen_before_update ON untergruppen;")
    op.execute("DROP TRIGGER IF EXISTS trg_hauptgruppen_before_update ON hauptgruppen;")
    op.execute("DROP TRIGGER IF EXISTS trg_untergruppen_forbid_delete ON untergruppen;")
    op.execute("DROP TRIGGER IF EXISTS trg_hauptgruppen_forbid_delete ON hauptgruppen;")
    op.execute("DROP FUNCTION IF EXISTS untergruppen_before_update();")
    op.execute("DROP FUNCTION IF EXISTS hauptgruppen_before_update();")
    op.execute("DROP FUNCTION IF EXISTS forbid_hard_delete_gruppen();")
    op.drop_table("gruppen_audit")
    op.drop_table("gruppen_aliases")
    op.drop_table("untergruppen")
    op.drop_table("hauptgruppen")
