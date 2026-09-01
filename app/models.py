"""ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

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
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
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
