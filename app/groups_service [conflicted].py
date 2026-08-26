"""Group registry: resolution helpers and write operations.

Pure functions over a Session so week 3 can import them without HTTP.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import GruppenAlias, GruppenAudit, Hauptgruppe, Untergruppe

CODE_RE = re.compile(r"^[0-9]{3}$")
_WHITESPACE_RE = re.compile(r"\s+")

MSG_CODE_LOCKED = "Es befinden sich bereits Artikel in dieser Hauptgruppe"
MSG_CODE_LOCKED_UNTERGRUPPE = "Es befinden sich bereits Artikel in dieser Untergruppe"
MSG_CODE_TAKEN = "Code bereits vergeben"
MSG_CODE_FORMAT = "Code muss aus genau drei Ziffern bestehen"
MSG_CHILDREN_FIRST = "Untergruppen müssen zuerst gelöscht werden"
MSG_ALIAS_TAKEN = "Alias bereits vergeben"
MSG_ALIAS_EMPTY = "Alias darf nicht leer sein"
MSG_NAME_EMPTY = "Bezeichnung darf nicht leer sein"
MSG_PARENT_LOCKED = "Zuordnung zur Hauptgruppe gesperrt: bereits von Artikeln verwendet"


class AmbiguousGroupMatch(ValueError):
    """Raised when a lookup string matches more than one group."""


class GroupRegistryError(Exception):
    """A registry write was rejected. ``message`` is the German UI string."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def normalize_alias(text: str) -> str:
    """Uppercase, collapse internal whitespace, strip."""
    return _WHITESPACE_RE.sub(" ", str(text).strip()).upper()


def _require_code(code: str) -> str:
    cleaned = str(code).strip()
    if not CODE_RE.fullmatch(cleaned):
        raise GroupRegistryError(MSG_CODE_FORMAT)
    return cleaned


def _require_name(name: str) -> str:
    cleaned = str(name).strip()
    if not cleaned:
        raise GroupRegistryError(MSG_NAME_EMPTY)
    return cleaned


def _not_deleted(query: Select[Any], model: type[Hauptgruppe | Untergruppe]) -> Select[Any]:
    return query.where(model.deleted_at.is_(None))


def _one_or_ambiguous(rows: list[Any], needle: str) -> Any | None:
    if len(rows) > 1:
        raise AmbiguousGroupMatch(f"Lookup {needle!r} matches {len(rows)} groups")
    if len(rows) == 1:
        return rows[0]
    return None


def resolve_hauptgruppe(
    db: Session,
    text: str,
    *,
    include_deleted: bool = False,
) -> Hauptgruppe | None:
    """Match exact code, then exact name, then normalized alias."""
    needle = str(text).strip()
    if not needle:
        return None

    def scoped(query: Select[Any]) -> Select[Any]:
        if include_deleted:
            return query
        return _not_deleted(query, Hauptgruppe)

    rows = list(db.scalars(scoped(select(Hauptgruppe).where(Hauptgruppe.code == needle))))
    hit = _one_or_ambiguous(rows, needle)
    if hit is not None:
        return hit

    rows = list(db.scalars(scoped(select(Hauptgruppe).where(Hauptgruppe.name == needle))))
    hit = _one_or_ambiguous(rows, needle)
    if hit is not None:
        return hit

    key = normalize_alias(needle)
    query = (
        select(Hauptgruppe)
        .join(GruppenAlias, GruppenAlias.hauptgruppe_id == Hauptgruppe.id)
        .where(GruppenAlias.alias_normalized == key)
    )
    rows = list(db.scalars(scoped(query)))
    return _one_or_ambiguous(rows, needle)


def resolve_untergruppe(
    db: Session,
    hauptgruppe: Hauptgruppe,
    text: str,
    *,
    include_deleted: bool = False,
) -> Untergruppe | None:
    """Match exact code, then exact name, then normalized alias, scoped to parent."""
    needle = str(text).strip()
    if not needle:
        return None

    def scoped(query: Select[Any]) -> Select[Any]:
        query = query.where(Untergruppe.hauptgruppe_id == hauptgruppe.id)
        if include_deleted:
            return query
        return _not_deleted(query, Untergruppe)

    rows = list(db.scalars(scoped(select(Untergruppe).where(Untergruppe.code == needle))))
    hit = _one_or_ambiguous(rows, needle)
    if hit is not None:
        return hit

    rows = list(db.scalars(scoped(select(Untergruppe).where(Untergruppe.name == needle))))
    hit = _one_or_ambiguous(rows, needle)
    if hit is not None:
        return hit

    key = normalize_alias(needle)
    query = (
        select(Untergruppe)
        .join(GruppenAlias, GruppenAlias.untergruppe_id == Untergruppe.id)
        .where(GruppenAlias.alias_normalized == key)
    )
    rows = list(db.scalars(scoped(query)))
    return _one_or_ambiguous(rows, needle)


def list_active_hauptgruppen(db: Session) -> list[Hauptgruppe]:
    stmt = (
        select(Hauptgruppe)
        .where(Hauptgruppe.deleted_at.is_(None))
        .order_by(Hauptgruppe.code)
    )
    return list(db.scalars(stmt))


def list_active_untergruppen(db: Session, hauptgruppe_id: uuid.UUID) -> list[Untergruppe]:
    stmt = (
        select(Untergruppe)
        .where(
            Untergruppe.hauptgruppe_id == hauptgruppe_id,
            Untergruppe.deleted_at.is_(None),
        )
        .order_by(Untergruppe.code)
    )
    return list(db.scalars(stmt))


def count_active_untergruppen(db: Session, hauptgruppe_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not hauptgruppe_ids:
        return {}
    stmt = (
        select(Untergruppe.hauptgruppe_id, func.count(Untergruppe.id))
        .where(
            Untergruppe.hauptgruppe_id.in_(hauptgruppe_ids),
            Untergruppe.deleted_at.is_(None),
        )
        .group_by(Untergruppe.hauptgruppe_id)
    )
    return {row[0]: int(row[1]) for row in db.execute(stmt)}


def list_hauptgruppen(db: Session, *, include_deleted: bool = False) -> list[Hauptgruppe]:
    stmt = select(Hauptgruppe).order_by(Hauptgruppe.code)
    if not include_deleted:
        stmt = stmt.where(Hauptgruppe.deleted_at.is_(None))
    return list(db.scalars(stmt))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def snapshot_hauptgruppe(group: Hauptgruppe) -> dict[str, Any]:
    return {
        "id": str(group.id),
        "code": group.code,
        "name": group.name,
        "locked_at": _iso(group.locked_at),
        "deleted_at": _iso(group.deleted_at),
    }


def snapshot_untergruppe(group: Untergruppe) -> dict[str, Any]:
    return {
        "id": str(group.id),
        "hauptgruppe_id": str(group.hauptgruppe_id),
        "code": group.code,
        "name": group.name,
        "locked_at": _iso(group.locked_at),
        "deleted_at": _iso(group.deleted_at),
    }


def snapshot_alias(alias: GruppenAlias) -> dict[str, Any]:
    return {
        "id": str(alias.id),
        "alias": alias.alias,
        "alias_normalized": alias.alias_normalized,
        "hauptgruppe_id": str(alias.hauptgruppe_id) if alias.hauptgruppe_id else None,
        "untergruppe_id": str(alias.untergruppe_id) if alias.untergruppe_id else None,
    }


def record_audit(
    db: Session,
    *,
    entity: str,
    entity_id: uuid.UUID,
    action: str,
    actor: Mapping[str, Any],
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> GruppenAudit:
    row = GruppenAudit(
        entity=entity,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        actor_oid=str(actor["oid"]),
        actor_name=str(actor["name"]),
    )
    db.add(row)
    return row


def german_db_error(exc: BaseException) -> str | None:
    """Map a Postgres trigger/constraint failure to a German UI sentence."""
    orig = getattr(exc, "orig", exc)
    text = str(orig)
    diag = getattr(orig, "diag", None)
    primary = getattr(diag, "message_primary", None) if diag is not None else None
    combined = f"{primary or ''} {text}"
    if "group code is locked" in combined:
        return MSG_CODE_LOCKED
    if "group parent is locked" in combined:
        return MSG_PARENT_LOCKED
    if "cannot soft-delete hauptgruppe with live untergruppen" in combined:
        return MSG_CHILDREN_FIRST
    if "uq_hauptgruppen_code_active" in combined:
        return MSG_CODE_TAKEN
    if "uq_untergruppen_parent_code_active" in combined:
        return MSG_CODE_TAKEN
    if "uq_gruppen_aliases_normalized" in combined:
        return MSG_ALIAS_TAKEN
    if "ck_hauptgruppen_code" in combined or "ck_untergruppen_code" in combined:
        return MSG_CODE_FORMAT
    return None


def flush_registry(db: Session) -> None:
    """Flush and convert constraint/trigger failures into GroupRegistryError."""
    try:
        db.flush()
    except (IntegrityError, DBAPIError) as exc:
        message = german_db_error(exc)
        if message is None:
            raise
        raise GroupRegistryError(message) from exc


def create_hauptgruppe(db: Session, *, code: str, name: str, actor: Mapping[str, Any]) -> Hauptgruppe:
    group = Hauptgruppe(code=_require_code(code), name=_require_name(name))
    db.add(group)
    flush_registry(db)
    record_audit(
        db,
        entity="hauptgruppe",
        entity_id=group.id,
        action="created",
        actor=actor,
        after=snapshot_hauptgruppe(group),
    )
    flush_registry(db)
    return group


def rename_hauptgruppe(
    db: Session, group: Hauptgruppe, *, name: str, actor: Mapping[str, Any]
) -> Hauptgruppe:
    cleaned = _require_name(name)
    if group.name == cleaned:
        return group
    before = snapshot_hauptgruppe(group)
    group.name = cleaned
    flush_registry(db)
    record_audit(
        db,
        entity="hauptgruppe",
        entity_id=group.id,
        action="renamed",
        actor=actor,
        before=before,
        after=snapshot_hauptgruppe(group),
    )
    flush_registry(db)
    return group


def change_hauptgruppe_code(
    db: Session, group: Hauptgruppe, *, code: str, actor: Mapping[str, Any]
) -> Hauptgruppe:
    cleaned = _require_code(code)
    if group.locked_at is not None:
        raise GroupRegistryError(MSG_CODE_LOCKED)
    if group.code == cleaned:
        return group
    before = snapshot_hauptgruppe(group)
    group.code = cleaned
    flush_registry(db)
    record_audit(
        db,
        entity="hauptgruppe",
        entity_id=group.id,
        action="renamed",
        actor=actor,
        before=before,
        after=snapshot_hauptgruppe(group),
    )
    flush_registry(db)
    return group


def soft_delete_hauptgruppe(
    db: Session, group: Hauptgruppe, *, actor: Mapping[str, Any]
) -> Hauptgruppe:
    if group.deleted_at is not None:
        return group
    before = snapshot_hauptgruppe(group)
    group.deleted_at = datetime.now(UTC)
    flush_registry(db)
    record_audit(
        db,
        entity="hauptgruppe",
        entity_id=group.id,
        action="deleted",
        actor=actor,
        before=before,
        after=snapshot_hauptgruppe(group),
    )
    flush_registry(db)
    return group


def restore_hauptgruppe(db: Session, group: Hauptgruppe, *, actor: Mapping[str, Any]) -> Hauptgruppe:
    if group.deleted_at is None:
        return group
    before = snapshot_hauptgruppe(group)
    group.deleted_at = None
    flush_registry(db)
    record_audit(
        db,
        entity="hauptgruppe",
        entity_id=group.id,
        action="restored",
        actor=actor,
        before=before,
        after=snapshot_hauptgruppe(group),
    )
    flush_registry(db)
    return group


def create_untergruppe(
    db: Session,
    parent: Hauptgruppe,
    *,
    code: str,
    name: str,
    actor: Mapping[str, Any],
) -> Untergruppe:
    group = Untergruppe(
        hauptgruppe_id=parent.id,
        code=_require_code(code),
        name=_require_name(name),
    )
    db.add(group)
    flush_registry(db)
    record_audit(
        db,
        entity="untergruppe",
        entity_id=group.id,
        action="created",
        actor=actor,
        after=snapshot_untergruppe(group),
    )
    flush_registry(db)
    return group


def rename_untergruppe(
    db: Session, group: Untergruppe, *, name: str, actor: Mapping[str, Any]
) -> Untergruppe:
    cleaned = _require_name(name)
    if group.name == cleaned:
        return group
    before = snapshot_untergruppe(group)
    group.name = cleaned
    flush_registry(db)
    record_audit(
        db,
        entity="untergruppe",
        entity_id=group.id,
        action="renamed",
        actor=actor,
        before=before,
        after=snapshot_untergruppe(group),
    )
    flush_registry(db)
    return group


def change_untergruppe_code(
    db: Session, group: Untergruppe, *, code: str, actor: Mapping[str, Any]
) -> Untergruppe:
    cleaned = _require_code(code)
    if group.locked_at is not None:
        raise GroupRegistryError(MSG_CODE_LOCKED_UNTERGRUPPE)
    if group.code == cleaned:
        return group
    before = snapshot_untergruppe(group)
    group.code = cleaned
    flush_registry(db)
    record_audit(
        db,
        entity="untergruppe",
        entity_id=group.id,
        action="renamed",
        actor=actor,
        before=before,
        after=snapshot_untergruppe(group),
    )
    flush_registry(db)
    return group


def soft_delete_untergruppe(
    db: Session, group: Untergruppe, *, actor: Mapping[str, Any]
) -> Untergruppe:
    if group.deleted_at is not None:
        return group
    before = snapshot_untergruppe(group)
    group.deleted_at = datetime.now(UTC)
    flush_registry(db)
    record_audit(
        db,
        entity="untergruppe",
        entity_id=group.id,
        action="deleted",
        actor=actor,
        before=before,
        after=snapshot_untergruppe(group),
    )
    flush_registry(db)
    return group


def restore_untergruppe(
    db: Session, group: Untergruppe, *, actor: Mapping[str, Any]
) -> Untergruppe:
    if group.deleted_at is None:
        return group
    before = snapshot_untergruppe(group)
    group.deleted_at = None
    flush_registry(db)
    record_audit(
        db,
        entity="untergruppe",
        entity_id=group.id,
        action="restored",
        actor=actor,
        before=before,
        after=snapshot_untergruppe(group),
    )
    flush_registry(db)
    return group


def add_alias(
    db: Session,
    *,
    alias: str,
    actor: Mapping[str, Any],
    hauptgruppe: Hauptgruppe | None = None,
    untergruppe: Untergruppe | None = None,
) -> GruppenAlias:
    original = str(alias).strip()
    if not original:
        raise GroupRegistryError(MSG_ALIAS_EMPTY)
    if (hauptgruppe is None) == (untergruppe is None):
        raise ValueError("Exactly one of hauptgruppe or untergruppe is required")
    row = GruppenAlias(
        alias=original,
        alias_normalized=normalize_alias(original),
        hauptgruppe_id=hauptgruppe.id if hauptgruppe is not None else None,
        untergruppe_id=untergruppe.id if untergruppe is not None else None,
    )
    db.add(row)
    flush_registry(db)
    record_audit(
        db,
        entity="alias",
        entity_id=row.id,
        action="alias_added",
        actor=actor,
        after=snapshot_alias(row),
    )
    flush_registry(db)
    return row


def remove_alias(db: Session, alias: GruppenAlias, *, actor: Mapping[str, Any]) -> None:
    before = snapshot_alias(alias)
    entity_id = alias.id
    db.delete(alias)
    flush_registry(db)
    record_audit(
        db,
        entity="alias",
        entity_id=entity_id,
        action="alias_removed",
        actor=actor,
        before=before,
    )
    flush_registry(db)
