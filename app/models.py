"""ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_oid: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_name: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_jobs_status",
        ),
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_status_heartbeat", "status", "heartbeat_at"),
    )


class UserWeclappToken(Base):
    """Per-Entra-oid weclapp API token. Credential only — not a users table."""

    __tablename__ = "user_weclapp_tokens"

    oid: Mapped[str] = mapped_column(Text, primary_key=True)
    token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    last_verified_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Hauptgruppe(Base):
    __tablename__ = "hauptgruppen"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Set by article registration (week 3) the first time a number is issued
    # under this group. Nothing in week 2 writes this column.
    locked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    untergruppen: Mapped[list[Untergruppe]] = relationship(back_populates="hauptgruppe")
    aliases: Mapped[list[GruppenAlias]] = relationship(
        back_populates="hauptgruppe",
        foreign_keys="GruppenAlias.hauptgruppe_id",
    )

    __table_args__ = (
        CheckConstraint("code ~ '^[0-9]{3}$'", name="ck_hauptgruppen_code"),
        Index(
            "uq_hauptgruppen_code_active",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Untergruppe(Base):
    __tablename__ = "untergruppen"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    hauptgruppe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hauptgruppen.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Set by article registration (week 3) the first time a number is issued
    # under this group. Nothing in week 2 writes this column.
    locked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    hauptgruppe: Mapped[Hauptgruppe] = relationship(back_populates="untergruppen")
    aliases: Mapped[list[GruppenAlias]] = relationship(
        back_populates="untergruppe",
        foreign_keys="GruppenAlias.untergruppe_id",
    )

    __table_args__ = (
        CheckConstraint("code ~ '^[0-9]{3}$'", name="ck_untergruppen_code"),
        Index(
            "uq_untergruppen_parent_code_active",
            "hauptgruppe_id",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class GruppenAlias(Base):
    __tablename__ = "gruppen_aliases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    hauptgruppe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hauptgruppen.id", ondelete="RESTRICT"),
        nullable=True,
    )
    untergruppe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("untergruppen.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    hauptgruppe: Mapped[Hauptgruppe | None] = relationship(
        back_populates="aliases",
        foreign_keys=[hauptgruppe_id],
    )
    untergruppe: Mapped[Untergruppe | None] = relationship(
        back_populates="aliases",
        foreign_keys=[untergruppe_id],
    )

    __table_args__ = (
        CheckConstraint(
            "(hauptgruppe_id IS NOT NULL AND untergruppe_id IS NULL)"
            " OR (hauptgruppe_id IS NULL AND untergruppe_id IS NOT NULL)",
            name="ck_gruppen_aliases_one_target",
        ),
        Index(
            "uq_gruppen_aliases_normalized_hauptgruppe",
            "alias_normalized",
            unique=True,
            postgresql_where=text("hauptgruppe_id IS NOT NULL"),
        ),
        Index(
            "uq_gruppen_aliases_normalized_untergruppe",
            "alias_normalized",
            unique=True,
            postgresql_where=text("untergruppe_id IS NOT NULL"),
        ),
    )


class GruppenAudit(Base):
    __tablename__ = "gruppen_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    actor_oid: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "entity IN ('hauptgruppe', 'untergruppe', 'alias')",
            name="ck_gruppen_audit_entity",
        ),
        CheckConstraint(
            "action IN ("
            "'created', 'renamed', 'deleted', 'restored', "
            "'alias_added', 'alias_removed', 'locked_by_backfill', "
            "'locked_by_registration'"
            ")",
            name="ck_gruppen_audit_action",
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    actor_oid: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_occurred_at", "occurred_at"),
    )


class ArticleTemplate(Base):
    __tablename__ = "article_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    columns: Mapped[list] = mapped_column(JSONB, nullable=False)
    xlsx_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_by_oid: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_name: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    batches: Mapped[list[ArticleBatch]] = relationship(back_populates="template")

    __table_args__ = (
        Index(
            "uq_article_templates_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


class ArticleBatch(Base):
    __tablename__ = "article_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_templates.id"),
        nullable=False,
    )
    created_by_oid: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    approved_by_oid: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    submitted_by_oid: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped[ArticleTemplate] = relationship(back_populates="batches")
    rows: Mapped[list[ArticleBatchRow]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ArticleBatchRow.position",
    )
    presence: Mapped[list[ArticleBatchPresence]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'submitting', 'submitted', 'discarded')",
            name="ck_article_batches_status",
        ),
        Index("ix_article_batches_source_sha256", "source_sha256"),
    )


class ArticleBatchRow(Base):
    __tablename__ = "article_batch_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    edits: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    proposed_article_number: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    include: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    validation_error: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    resolved_hauptgruppe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hauptgruppen.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_untergruppe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("untergruppen.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    weclapp_article_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    write_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    submitted_by_oid: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch: Mapped[ArticleBatch] = relationship(back_populates="rows")

    __table_args__ = (
        Index("ix_article_batch_rows_batch_position", "batch_id", "position"),
    )


class ArticleSnapshot(Base):
    __tablename__ = "article_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_by_oid: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_name: Mapped[str] = mapped_column(Text, nullable=False)
    weclapp_tenant: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    columns: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    non_conforming_number_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    rows: Mapped[list[ArticleSnapshotRow]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="ArticleSnapshotRow.position",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'complete', 'failed')",
            name="ck_article_snapshots_status",
        ),
        Index("ix_article_snapshots_tenant_created", "weclapp_tenant", "created_at"),
    )


class ArticleSnapshotRow(Base):
    __tablename__ = "article_snapshot_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    article_number: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    article_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    hauptgruppe_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    untergruppe_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    weclapp_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    weclapp_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot: Mapped[ArticleSnapshot] = relationship(back_populates="rows")

    __table_args__ = (
        Index("ix_article_snapshot_rows_snapshot_position", "snapshot_id", "position"),
        Index(
            "ix_article_snapshot_rows_snapshot_hauptgruppe",
            "snapshot_id",
            "hauptgruppe_code",
        ),
        Index(
            "ix_article_snapshot_rows_snapshot_untergruppe",
            "snapshot_id",
            "untergruppe_code",
        ),
    )


class ArticleBatchPresence(Base):
    __tablename__ = "article_batch_presence"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_batches.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_oid: Mapped[str] = mapped_column(Text, primary_key=True)
    user_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    batch: Mapped[ArticleBatch] = relationship(back_populates="presence")


class FieldAlias(Base):
    __tablename__ = "field_alias"

    field_key: Mapped[str] = mapped_column(Text, primary_key=True)
    label_internal: Mapped[str] = mapped_column(Text, nullable=False)
    label_weclapp: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    weclapp_column: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    write_policy: Mapped[str] = mapped_column(Text, nullable=False)
    edit_policy: Mapped[str] = mapped_column(Text, nullable=False)
    default_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    phase: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    __table_args__ = (
        CheckConstraint(
            "scope IN ('supply_source', 'article', 'derived', 'context')",
            name="ck_field_alias_scope",
        ),
        CheckConstraint(
            "write_policy IN ('always', 'on_value', 'locked')",
            name="ck_field_alias_write_policy",
        ),
        CheckConstraint(
            "edit_policy IN ('editable', 'read_only', 'derived')",
            name="ck_field_alias_edit_policy",
        ),
        CheckConstraint("phase IN (1, 2)", name="ck_field_alias_phase"),
    )


class UserPreference(Base):
    """Per-user, per-tool UI preferences. Never stored on run state."""

    __tablename__ = "user_preference"

    user_oid: Mapped[str] = mapped_column(Text, primary_key=True)
    tool_key: Mapped[str] = mapped_column(Text, primary_key=True)
    pref_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DiscountCategory(Base):
    __tablename__ = "discount_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[str] = mapped_column(Text, nullable=False)
    category_code: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    customer_discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_by: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "supplier_id",
            "category_code",
            "valid_from",
            name="uq_discount_category_supplier_code_from",
        ),
        Index(
            "ix_discount_category_supplier_code_current",
            "supplier_id",
            "category_code",
            postgresql_where=text("valid_to IS NULL"),
        ),
    )


class ExportRun(Base):
    __tablename__ = "export_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    created_by_oid: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_name: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_id: Mapped[str] = mapped_column(Text, nullable=False)
    filter_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    file: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    included_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sales_article_currency: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    markup_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("50"),
        server_default="50",
    )
    eur_chf_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("0.9300"),
        server_default="0.9300",
    )
    eur_chf_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    rows: Mapped[list[ExportRow]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ExportRow.position",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'draft', 'exported', 'failed')",
            name="ck_export_run_status",
        ),
        Index("ix_export_run_supplier_created", "supplier_id", "created_at"),
        Index(
            "uq_export_run_supplier_running",
            "supplier_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )


class ExportRow(Base):
    __tablename__ = "export_row"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("export_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    article_number: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    supplier_article_number: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    supplier_number: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    article_name: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    ek_price_before_discount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    matchcode: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    discount_category: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    discount_category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("discount_category.id", ondelete="SET NULL"),
        nullable=True,
    )
    base_discount_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    customer_discount_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    discount_intent: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unresolved",
        server_default="unresolved",
    )
    row_intent: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="update",
        server_default="update",
    )
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    included: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    weclapp_supply_source_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    weclapp_current_ek: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    weclapp_current_base_discount_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    weclapp_current_customer_discount_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    weclapp_current_is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    hauptgruppe_code: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    untergruppe_code: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    extras: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    article_context: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    dropshipping_possible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    weclapp_current_dropshipping: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    run: Mapped[ExportRun] = relationship(back_populates="rows")

    __table_args__ = (
        CheckConstraint(
            "discount_intent IN ('apply', 'zero', 'unresolved')",
            name="ck_export_row_discount_intent",
        ),
        CheckConstraint(
            "row_intent IN ('update', 'create')",
            name="ck_export_row_row_intent",
        ),
        UniqueConstraint(
            "run_id",
            "article_number",
            "supplier_article_number",
            name="uq_export_row_run_article_supplier_article",
        ),
        Index("ix_export_row_run_position", "run_id", "position"),
        Index("ix_export_row_run_included", "run_id", "included"),
        Index("ix_export_row_run_discount_category", "run_id", "discount_category"),
    )


class AssistantQuery(Base):
    """One article-assistant question. Survives snapshot retention."""

    __tablename__ = "assistant_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    asked_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    user_oid: Mapped[str] = mapped_column(Text, nullable=False)
    user_name: Mapped[str] = mapped_column(Text, nullable=False)
    question_de: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_calls: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    answer_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_article_numbers: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    applied_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    selection_truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    __table_args__ = (
        CheckConstraint(
            "outcome IN ("
            "'answered','answered_unverified','no_result','no_answer',"
            "'refused','invalid_input','error','unavailable'"
            ")",
            name="ck_assistant_queries_outcome",
        ),
        Index("ix_assistant_queries_asked_at", "asked_at"),
    )


class TransformRun(Base):
    __tablename__ = "transform_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_by_oid: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_variants: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    word_positions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    rows: Mapped[list["TransformRow"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list["TransformChunk"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('previewing', 'previewed', 'failed')",
            name="ck_transform_runs_status",
        ),
        Index("ix_transform_runs_created_at", "created_at"),
        Index("ix_transform_runs_snapshot", "snapshot_id"),
    )


class TransformRow(Base):
    __tablename__ = "transform_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transform_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    article_number: Mapped[str] = mapped_column(Text, nullable=False)
    weclapp_id: Mapped[str] = mapped_column(Text, nullable=False)
    version_at_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    operations_fired: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    row_status: Mapped[str] = mapped_column(Text, nullable=False)
    apply_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_detail: Mapped[Any] = mapped_column(JSONB, nullable=True)
    apply_version_seen: Mapped[str | None] = mapped_column(Text, nullable=True)
    inside_compound: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    run: Mapped[TransformRun] = relationship(back_populates="rows")

    __table_args__ = (
        CheckConstraint(
            "row_status IN ('CHANGED', 'UNCHANGED', 'REFUSED', 'GONE', 'DECLINED')",
            name="ck_transform_rows_status",
        ),
        CheckConstraint(
            "apply_outcome IS NULL OR apply_outcome IN ("
            "'UPDATED','UNCHANGED','CONFLICT','REJECTED','GONE',"
            "'REFUSED','UNAVAILABLE','UNKNOWN'"
            ")",
            name="ck_transform_rows_apply_outcome",
        ),
        Index("ix_transform_rows_run", "run_id"),
        Index("ix_transform_rows_run_article", "run_id", "article_number"),
    )


class TransformChunk(Base):
    __tablename__ = "transform_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transform_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    approved_by_oid: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[TransformRun] = relationship(back_populates="chunks")

    __table_args__ = (
        CheckConstraint(
            "status IN ('approved', 'applying', 'applied', 'failed')",
            name="ck_transform_chunks_status",
        ),
        UniqueConstraint("run_id", "chunk_index", name="uq_transform_chunks_run_index"),
        Index("ix_transform_chunks_run", "run_id"),
    )


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_number: Mapped[str] = mapped_column(Text, nullable=False)
    weclapp_party_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    einkaufswaehrung: Mapped[str] = mapped_column(Text, nullable=False)
    default_kurs: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    # MARKUP (0.50 → × 1.50), not a margin.
    default_aufschlag: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    default_verkaufswaehrung: Mapped[str] = mapped_column(
        Text, nullable=False, default="CHF", server_default="CHF"
    )
    default_unit_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("supplier_number", name="uq_suppliers_supplier_number"),
        UniqueConstraint("weclapp_party_id", name="uq_suppliers_weclapp_party_id"),
        CheckConstraint(
            "einkaufswaehrung IN ('EUR', 'CHF')",
            name="ck_suppliers_einkaufswaehrung",
        ),
        CheckConstraint(
            "default_verkaufswaehrung IN ('EUR', 'CHF')",
            name="ck_suppliers_default_verkaufswaehrung",
        ),
        CheckConstraint("default_kurs > 0", name="ck_suppliers_default_kurs_positive"),
        CheckConstraint(
            "default_aufschlag >= 0",
            name="ck_suppliers_default_aufschlag_nonnegative",
        ),
        CheckConstraint(
            "einkaufswaehrung <> 'CHF' OR default_kurs = 1.0",
            name="ck_suppliers_chf_kurs_unity",
        ),
    )


class SuppliersAudit(Base):
    __tablename__ = "suppliers_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    actor_oid: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("entity IN ('supplier')", name="ck_suppliers_audit_entity"),
        CheckConstraint(
            "action IN ('created', 'renamed', 'updated', 'deleted', 'restored')",
            name="ck_suppliers_audit_action",
        ),
    )


class SupplySourceRun(Base):
    __tablename__ = "supply_source_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, default="pull", server_default="pull"
    )
    datenstand: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    einkaufswaehrung: Mapped[str] = mapped_column(Text, nullable=False)
    kurs: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    verkaufswaehrung: Mapped[str] = mapped_column(Text, nullable=False)
    # MARKUP fraction snapshotted at creation; never re-read from suppliers.
    aufschlag: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    preis_eintritt: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_name: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    chunk_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default="50"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    supplier: Mapped[Supplier] = relationship()
    rows: Mapped[list["SupplySourceRow"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','preview','approved','applying','applied','failed')",
            name="ck_supply_source_run_status",
        ),
        CheckConstraint("source IN ('pull','upload')", name="ck_supply_source_run_source"),
        CheckConstraint(
            "einkaufswaehrung IN ('EUR','CHF')",
            name="ck_supply_source_run_einkaufswaehrung",
        ),
        CheckConstraint(
            "verkaufswaehrung IN ('EUR','CHF')",
            name="ck_supply_source_run_verkaufswaehrung",
        ),
        CheckConstraint("kurs > 0", name="ck_supply_source_run_kurs_positive"),
        CheckConstraint(
            "aufschlag >= 0", name="ck_supply_source_run_aufschlag_nonnegative"
        ),
        CheckConstraint(
            "einkaufswaehrung <> 'CHF' OR kurs = 1.0",
            name="ck_supply_source_run_chf_kurs_unity",
        ),
        Index("ix_supply_source_run_supplier_created", "supplier_id", "created_at"),
        Index(
            "uq_supply_source_run_supplier_busy",
            "supplier_id",
            unique=True,
            postgresql_where=text("status IN ('running','applying')"),
        ),
    )


class SupplySourceRow(Base):
    __tablename__ = "supply_source_row"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_source_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_article_number: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ean: Mapped[str | None] = mapped_column(Text, nullable=True)
    listenpreis: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    rabatt_1: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    rabatt_2: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    discount_set: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    discount_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    rabattcode: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="unmatched", server_default="unmatched"
    )
    row_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_article_numbers: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    weclapp_article_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    weclapp_supply_source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    weclapp_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_ek: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    current_ek_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    vk_override: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_supply_source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    chunk_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    run: Mapped[SupplySourceRun] = relationship(back_populates="rows")

    __table_args__ = (
        CheckConstraint(
            "rabatt_1 IS NULL OR (rabatt_1 >= 0 AND rabatt_1 < 1)",
            name="ck_supply_source_row_rabatt_1",
        ),
        CheckConstraint(
            "rabatt_2 IS NULL OR (rabatt_2 >= 0 AND rabatt_2 < 1)",
            name="ck_supply_source_row_rabatt_2",
        ),
        CheckConstraint(
            "discount_source IS NULL OR discount_source IN ('manual','carried')",
            name="ck_supply_source_row_discount_source",
        ),
        CheckConstraint(
            "match_tier IS NULL OR (match_tier >= 1 AND match_tier <= 4)",
            name="ck_supply_source_row_match_tier",
        ),
        CheckConstraint(
            "match_status IN ('matched','unmatched')",
            name="ck_supply_source_row_match_status",
        ),
        CheckConstraint(
            "row_intent IS NULL OR row_intent IN "
            "('update','price_only','create','attach','renumber','skip')",
            name="ck_supply_source_row_row_intent",
        ),
        CheckConstraint(
            "apply_outcome IS NULL OR apply_outcome IN ("
            "'UPDATED','PRICE_UPDATED','UNCHANGED','CREATED','ATTACHED',"
            "'RENUMBERED','CONFLICT','REJECTED','GONE','AUTH','UNKNOWN'"
            ")",
            name="ck_supply_source_row_apply_outcome",
        ),
        UniqueConstraint(
            "run_id",
            "supplier_article_number",
            name="uq_supply_source_row_run_san",
        ),
        Index("ix_supply_source_row_run_id", "run_id"),
        Index("ix_supply_source_row_run_rabattcode", "run_id", "rabattcode"),
    )


class SupplierArticleAlias(Base):
    __tablename__ = "supplier_article_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_article_number: Mapped[str] = mapped_column(Text, nullable=False)
    article_number: Mapped[str] = mapped_column(Text, nullable=False)
    weclapp_article_id: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('supply_source', 'manual', 'ean', 'import')",
            name="ck_supplier_article_aliases_source",
        ),
        UniqueConstraint(
            "supplier_id",
            "supplier_article_number",
            "article_number",
            name="uq_supplier_article_aliases_triple",
        ),
    )


class SupplierArticleAliasesAudit(Base):
    __tablename__ = "supplier_article_aliases_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    actor_oid: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "entity IN ('alias')",
            name="ck_supplier_article_aliases_audit_entity",
        ),
        CheckConstraint(
            "action IN ('created', 'updated')",
            name="ck_supplier_article_aliases_audit_action",
        ),
    )


class WeclappUnit(Base):
    """Catalogue from GET /unit, rebuilt on each supply-source index."""

    __tablename__ = "weclapp_units"

    weclapp_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class WeclappArticle(Base):
    __tablename__ = "weclapp_articles"

    weclapp_article_id: Mapped[str] = mapped_column(Text, primary_key=True)
    article_number: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ean: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rabattcode: Mapped[str | None] = mapped_column(Text, nullable=True)
    weclapp_version: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    missing_since: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_weclapp_articles_article_number", "article_number"),
        Index("ix_weclapp_articles_ean", "ean"),
    )


class WeclappSupplySource(Base):
    __tablename__ = "weclapp_supply_sources"

    weclapp_id: Mapped[str] = mapped_column(Text, primary_key=True)
    supplier_party_id: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_number: Mapped[str] = mapped_column(Text, nullable=False)
    # SS.articleNumber — supplier's part number, not the PROSEMA article number.
    supplier_article_number: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_rate_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    ean: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_purchase_qty: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    fixed_purchase_qty: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    procurement_lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weclapp_version: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    missing_since: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "supplier_party_id",
            "supplier_article_number",
            name="uq_weclapp_supply_sources_party_san",
        ),
    )


class WeclappSupplySourcePrice(Base):
    __tablename__ = "weclapp_supply_source_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supply_source_weclapp_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("weclapp_supply_sources.weclapp_id", ondelete="CASCADE"),
        nullable=False,
    )
    weclapp_price_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    currency_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    reduction_additions: Mapped[Any | None] = mapped_column(JSONB, nullable=True)


class WeclappSupplySourceLink(Base):
    __tablename__ = "weclapp_supply_source_links"

    supply_source_weclapp_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("weclapp_supply_sources.weclapp_id", ondelete="CASCADE"),
        primary_key=True,
    )
    weclapp_article_id: Mapped[str] = mapped_column(Text, primary_key=True)
    article_number: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_party_id: Mapped[str] = mapped_column(Text, nullable=False)
    position_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (
        UniqueConstraint(
            "weclapp_article_id",
            "supplier_party_id",
            name="uq_weclapp_ss_links_article_supplier",
        ),
    )
