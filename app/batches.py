"""Batch grid: column config, merged row values, edits, numbering, presence."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.groups_service import (
    AmbiguousGroupMatch,
    list_active_hauptgruppen,
    list_active_untergruppen,
    resolve_hauptgruppe,
    resolve_untergruppe,
)
from app.models import ArticleBatch, ArticleBatchPresence, ArticleBatchRow
from core.numbering import Scheme
from scripts.weclapp.article_import import (
    DEFAULTS,
    IMPORT_COLUMNS,
    RESTRICTED_SELECT_COLUMNS,
    LookupTables,
    dropdown_options,
    row_to_payload,
)

JSPREADSHEET_CE_VERSION = "5.0.4"
JSUITES_VERSION = "5.13.5"

GRID_PAGE_SIZE = 250
PRESENCE_TTL = timedelta(seconds=20)
FLUSH_IDLE_MS = 400

MSG_FIELD_NOT_EDITABLE = "Feld nicht bearbeitbar"
MSG_BATCH_APPROVED = "Stapel bereits genehmigt — keine Änderungen möglich"
MSG_UNKNOWN_HAUPT = "Unbekannte Hauptgruppe"
MSG_UNKNOWN_UNTER = "Unbekannte Untergruppe"
MSG_MISSING_HAUPT = "Hauptgruppe fehlt"
MSG_MISSING_UNTER = "Untergruppe fehlt"

INCLUDE_FIELD = "include"
ARTICLE_NUMBER_FIELD = "Prosema Artikelnummer"
KURZTEXT_FIELD = "PROSEMA Kurztext"
HAUPTGRUPPE_FIELD = "Hauptgruppe"
UNTERGRUPPE_FIELD = "Untergruppe"
GROUP_FIELDS = {HAUPTGRUPPE_FIELD, UNTERGRUPPE_FIELD}

NEVER_EDITABLE = {
    ARTICLE_NUMBER_FIELD,
    "Produkt-ID (Prosema)",
    "Varianten-ID (Prosema)",
}

EDITABLE_WHITELIST: frozenset[str] = frozenset(
    column for column in IMPORT_COLUMNS if column not in NEVER_EDITABLE
) | {INCLUDE_FIELD}

SYNTHETIC_FIELDS = ("_zeile", "_status")

_LABEL_RE = re.compile(r"^(.*?)\s*-\s*(\d{3})\s*$")

COLUMN_WIDTHS: dict[str, int] = {
    "_zeile": 70,
    ARTICLE_NUMBER_FIELD: 160,
    KURZTEXT_FIELD: 220,
    "_status": 280,
    INCLUDE_FIELD: 100,
    "Lieferantenartikelnummer": 180,
    HAUPTGRUPPE_FIELD: 190,
    UNTERGRUPPE_FIELD: 210,
    "PROSEMA Langtext": 280,
    "Kurzbeschreibung": 200,
    "Referenz (Matchcode)": 160,
    "GTIN (EAN-Nummer)": 150,
    "Artikeltyp": 120,
    "Einheit": 90,
    "Kategorie": 180,
    "Aktiv": 80,
    "Im Verkauf": 100,
    "Steuersatz": 120,
    "Im Shop verfügbar": 140,
    "Im Shop aktiv": 120,
    "Bestand übertragen": 150,
    "Gewichtseinheit": 130,
    "Grundmaterial": 140,
    "Oberfläche": 130,
    "Farbe": 110,
    "Produktfamilie": 140,
    "Rabattcode": 110,
    "Verkaufseinheit": 130,
    "Verpackung": 120,
    "VPE 1": 80,
    "VPE 2": 80,
    "VPE 3": 80,
    "Breite in mm": 110,
    "Länge in cm": 110,
    "Höhe in mm": 100,
    "Bodenleger": 110,
    "Dachdecker": 120,
    "Landschaftsgärtner": 150,
    "Plattenleger": 120,
    "Artikelbeschreibung HTML": 210,
    "Nettogewicht kg": 130,
    "Produkt-ID (Prosema)": 160,
    "Varianten-ID (Prosema)": 160,
}

GRID_FIELD_ORDER: tuple[str, ...] = (
    "_zeile",
    ARTICLE_NUMBER_FIELD,
    KURZTEXT_FIELD,
    "_status",
    INCLUDE_FIELD,
    *(
        column
        for column in IMPORT_COLUMNS
        if column not in {ARTICLE_NUMBER_FIELD, KURZTEXT_FIELD}
    ),
)

COLUMN_TITLES: dict[str, str] = {
    "_zeile": "Zeile",
    "_status": "Status",
    INCLUDE_FIELD: "Übernehmen",
}


class BatchEditError(Exception):
    def __init__(self, message: str, *, field: str | None = None, status_code: int = 400):
        self.message = message
        self.field = field
        self.status_code = status_code
        super().__init__(message)


@dataclass
class CellEdit:
    row_id: uuid.UUID
    field: str
    value: Any


@dataclass
class RowEditResult:
    id: uuid.UUID
    proposed_article_number: str
    validation_error: str
    include: bool
    corrected: dict[str, Any] = field(default_factory=dict)


def group_label(name: str, code: str) -> str:
    return f"{name} - {code}"


def _split_group_label(text: str) -> tuple[str, str | None]:
    cleaned = str(text or "").strip()
    match = _LABEL_RE.match(cleaned)
    if match:
        return match.group(1).strip(), match.group(2)
    return cleaned, None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    return str(value)


def coerce_include(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text not in {"", "0", "false", "nein", "off", "no"}


def effective_values(row: ArticleBatchRow) -> dict[str, str]:
    merged: dict[str, str] = {}
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    edits = row.edits if isinstance(row.edits, dict) else {}
    for column in IMPORT_COLUMNS:
        if column in edits:
            merged[column] = _as_text(edits[column])
        elif column in raw:
            merged[column] = _as_text(raw[column])
        else:
            merged[column] = DEFAULTS.get(column, "")
    merged[ARTICLE_NUMBER_FIELD] = row.proposed_article_number or merged.get(
        ARTICLE_NUMBER_FIELD, ""
    )
    return merged


_LOOKUPS: LookupTables | None = None
_DROPDOWN_CACHE: dict[str, list[str]] | None = None


def _cached_lookups() -> LookupTables:
    global _LOOKUPS
    if _LOOKUPS is None:
        from scripts.weclapp.article_import import _load_schema

        _LOOKUPS = LookupTables(_load_schema())
    return _LOOKUPS


def schema_dropdowns() -> dict[str, list[str]]:
    global _DROPDOWN_CACHE
    if _DROPDOWN_CACHE is None:
        options = dropdown_options(_cached_lookups())
        options.pop(HAUPTGRUPPE_FIELD, None)
        options.pop(UNTERGRUPPE_FIELD, None)
        _DROPDOWN_CACHE = options
    return _DROPDOWN_CACHE


def group_dropdowns(db: Session) -> tuple[list[str], list[str]]:
    haupt: list[str] = []
    unter: list[str] = []
    for group in list_active_hauptgruppen(db):
        haupt.append(group_label(group.name, group.code))
        for child in list_active_untergruppen(db, group.id):
            unter.append(group_label(child.name, child.code))
    return haupt, unter


def build_columns(db: Session, *, editable: bool) -> list[dict[str, Any]]:
    schema_sources = schema_dropdowns()
    haupt, unter = group_dropdowns(db)
    sources = {
        **schema_sources,
        HAUPTGRUPPE_FIELD: haupt,
        UNTERGRUPPE_FIELD: unter,
    }
    columns: list[dict[str, Any]] = []
    for field_name in GRID_FIELD_ORDER:
        read_only = (
            (not editable)
            or field_name in SYNTHETIC_FIELDS
            or field_name not in EDITABLE_WHITELIST
        )
        column: dict[str, Any] = {
            "type": "text",
            "title": COLUMN_TITLES.get(field_name, field_name),
            "width": COLUMN_WIDTHS.get(field_name, 140),
            "readOnly": read_only,
            "name": field_name,
        }
        if field_name == INCLUDE_FIELD:
            column["type"] = "checkbox"
        elif field_name in sources:
            column["type"] = "dropdown"
            source = list(sources[field_name])
            if field_name not in RESTRICTED_SELECT_COLUMNS:
                source = [""] + source
            column["source"] = source
            if len(source) > 12:
                column["autocomplete"] = True
        columns.append(column)
    return columns


def grid_row_values(row: ArticleBatchRow) -> list[Any]:
    values = effective_values(row)
    out: list[Any] = []
    for field_name in GRID_FIELD_ORDER:
        if field_name == "_zeile":
            out.append(row.position)
        elif field_name == "_status":
            out.append(row.validation_error or "")
        elif field_name == INCLUDE_FIELD:
            out.append(bool(row.include))
        else:
            out.append(values.get(field_name, ""))
    return out


def resolve_row_groups(
    db: Session, values: dict[str, str]
) -> tuple[Any, Any, str | None]:
    raw_h = (values.get(HAUPTGRUPPE_FIELD) or "").strip()
    raw_u = (values.get(UNTERGRUPPE_FIELD) or "").strip()
    if not raw_h:
        return None, None, MSG_MISSING_HAUPT

    name, code = _split_group_label(raw_h)
    haupt = None
    try:
        if code:
            haupt = resolve_hauptgruppe(db, code)
        if haupt is None and name:
            haupt = resolve_hauptgruppe(db, name)
        if haupt is None:
            haupt = resolve_hauptgruppe(db, raw_h)
    except AmbiguousGroupMatch:
        return None, None, MSG_UNKNOWN_HAUPT
    if haupt is None:
        return None, None, MSG_UNKNOWN_HAUPT

    if not raw_u:
        return haupt, None, MSG_MISSING_UNTER

    uname, ucode = _split_group_label(raw_u)
    unter = None
    try:
        if ucode:
            unter = resolve_untergruppe(db, haupt, ucode)
        if unter is None and uname:
            unter = resolve_untergruppe(db, haupt, uname)
        if unter is None:
            unter = resolve_untergruppe(db, haupt, raw_u)
    except AmbiguousGroupMatch:
        return haupt, None, MSG_UNKNOWN_UNTER
    if unter is None:
        return haupt, None, MSG_UNKNOWN_UNTER
    return haupt, unter, None


def validate_effective(values: dict[str, str], group_error: str | None) -> str:
    messages: list[str] = []
    if group_error:
        messages.append(group_error)
    try:
        row_to_payload(values, _cached_lookups())
    except ValueError as exc:
        text = str(exc)
        if text not in messages:
            messages.append(text)
    return " ".join(messages)


def _number_matches(number: str, main: str, sub: str) -> bool:
    match = Scheme().pattern().match((number or "").strip())
    return bool(match and match.group(1) == main and match.group(2) == sub)


def _assign_numbers(
    rows: list[ArticleBatchRow], affected_ids: set[uuid.UUID]
) -> None:
    scheme = Scheme()
    pattern = scheme.pattern()
    need_new: list[ArticleBatchRow] = []
    reserved: dict[tuple[str, str], int] = {}

    for row in rows:
        existing = (row.proposed_article_number or "").strip()
        match = pattern.match(existing)
        haupt = getattr(row, "_resolved_haupt", None)
        unter = getattr(row, "_resolved_unter", None)
        if (
            row.id in affected_ids
            and haupt is not None
            and unter is not None
            and not _number_matches(existing, haupt.code, unter.code)
        ):
            need_new.append(row)
            continue
        if match:
            key = (match.group(1), match.group(2))
            reserved[key] = max(reserved.get(key, 0), int(match.group(3)))

    for row in need_new:
        haupt = row._resolved_haupt
        unter = row._resolved_unter
        key = (haupt.code, unter.code)
        current = reserved.get(key)
        nxt = scheme.start if current is None else current + scheme.step
        if nxt > scheme.max_running:
            row._group_error = (
                f"Gruppe {haupt.code}.{unter.code} hat das Maximum überschritten."
            )
            continue
        reserved[key] = nxt
        row.proposed_article_number = scheme.format(haupt.code, unter.code, nxt)


def _write_edit(row: ArticleBatchRow, field_name: str, value: Any) -> None:
    if field_name == INCLUDE_FIELD:
        row.include = coerce_include(value)
        return
    text = _as_text(value)
    current = dict(row.edits or {})
    current[field_name] = text
    row.edits = current


def _canonical_group_edits(row: ArticleBatchRow) -> dict[str, str]:
    corrected: dict[str, str] = {}
    edits = dict(row.edits or {})
    haupt = getattr(row, "_resolved_haupt", None)
    unter = getattr(row, "_resolved_unter", None)
    if haupt is not None:
        label = group_label(haupt.name, haupt.code)
        if effective_values(row).get(HAUPTGRUPPE_FIELD) != label:
            edits[HAUPTGRUPPE_FIELD] = label
            corrected[HAUPTGRUPPE_FIELD] = label
    if unter is not None:
        label = group_label(unter.name, unter.code)
        if effective_values(row).get(UNTERGRUPPE_FIELD) != label:
            edits[UNTERGRUPPE_FIELD] = label
            corrected[UNTERGRUPPE_FIELD] = label
    if corrected:
        row.edits = edits
    return corrected


def apply_edits(
    db: Session,
    batch: ArticleBatch,
    edits: list[CellEdit],
) -> list[RowEditResult]:
    if batch.status != "draft":
        raise BatchEditError(MSG_BATCH_APPROVED)

    for edit in edits:
        if edit.field not in EDITABLE_WHITELIST:
            raise BatchEditError(MSG_FIELD_NOT_EDITABLE, field=edit.field)

    rows = list(
        db.scalars(
            select(ArticleBatchRow)
            .where(ArticleBatchRow.batch_id == batch.id)
            .order_by(ArticleBatchRow.position)
            .with_for_update()
        )
    )
    by_id = {row.id: row for row in rows}

    affected: dict[uuid.UUID, ArticleBatchRow] = {}
    for edit in edits:
        row = by_id.get(edit.row_id)
        if row is None:
            raise BatchEditError("Zeile gehört nicht zu diesem Stapel", field=edit.field)
        affected[row.id] = row

    for edit in edits:
        _write_edit(by_id[edit.row_id], edit.field, edit.value)

    for row in affected.values():
        values = effective_values(row)
        haupt, unter, group_error = resolve_row_groups(db, values)
        row._resolved_haupt = haupt
        row._resolved_unter = unter
        row._group_error = group_error
        row.resolved_hauptgruppe_id = haupt.id if haupt is not None else None
        row.resolved_untergruppe_id = unter.id if unter is not None else None

    _assign_numbers(rows, set(affected))

    results: list[RowEditResult] = []
    for row in affected.values():
        corrected = _canonical_group_edits(row)
        values = effective_values(row)
        row.validation_error = validate_effective(values, getattr(row, "_group_error", None))
        results.append(
            RowEditResult(
                id=row.id,
                proposed_article_number=row.proposed_article_number or "",
                validation_error=row.validation_error or "",
                include=bool(row.include),
                corrected=corrected,
            )
        )
    batch.updated_at = datetime.now(UTC)
    return results


def row_matches(
    row: ArticleBatchRow,
    *,
    query: str = "",
    hauptgruppe: str = "",
    kategorie: str = "",
    aktiv: str = "",
    nur_fehler: bool = False,
) -> bool:
    if nur_fehler and not (row.validation_error or "").strip():
        return False
    values = effective_values(row)
    needle = query.strip().lower()
    if needle:
        haystack = " ".join(
            [
                values.get(ARTICLE_NUMBER_FIELD, ""),
                values.get("Lieferantenartikelnummer", ""),
                values.get(KURZTEXT_FIELD, ""),
                values.get("Referenz (Matchcode)", ""),
            ]
        ).lower()
        if needle not in haystack:
            return False
    if hauptgruppe and values.get(HAUPTGRUPPE_FIELD, "") != hauptgruppe:
        return False
    if kategorie and values.get("Kategorie", "") != kategorie:
        return False
    return not (aktiv and values.get("Aktiv", "") != aktiv)


def filtered_rows(
    rows: list[ArticleBatchRow],
    *,
    query: str = "",
    hauptgruppe: str = "",
    kategorie: str = "",
    aktiv: str = "",
    nur_fehler: bool = False,
    page: int = 1,
) -> tuple[list[ArticleBatchRow], int, int]:
    matched = [
        row
        for row in rows
        if row_matches(
            row,
            query=query,
            hauptgruppe=hauptgruppe,
            kategorie=kategorie,
            aktiv=aktiv,
            nur_fehler=nur_fehler,
        )
    ]
    total = len(matched)
    page = max(1, page)
    start = (page - 1) * GRID_PAGE_SIZE
    page_rows = matched[start : start + GRID_PAGE_SIZE]
    pages = max(1, (total + GRID_PAGE_SIZE - 1) // GRID_PAGE_SIZE) if total else 1
    return page_rows, total, pages


def build_grid_config(
    db: Session,
    batch: ArticleBatch,
    rows: list[ArticleBatchRow],
) -> dict[str, Any]:
    editable = batch.status == "draft"
    return {
        "editsUrl": f"/batches/{batch.id}/edits",
        "editable": editable,
        "parseFormulas": False,
        "freezeColumns": 3,
        "idleMs": FLUSH_IDLE_MS,
        "columns": build_columns(db, editable=editable),
        "data": [grid_row_values(row) for row in rows],
        "rowIds": [str(row.id) for row in rows],
        "rowState": [
            {
                "validation_error": row.validation_error or "",
                "include": bool(row.include),
            }
            for row in rows
        ],
        "fields": list(GRID_FIELD_ORDER),
    }


def touch_presence(db: Session, batch: ArticleBatch, user: dict[str, Any]) -> list[str]:
    now = datetime.now(UTC)
    cutoff = now - PRESENCE_TTL
    db.execute(
        delete(ArticleBatchPresence).where(
            ArticleBatchPresence.batch_id == batch.id,
            ArticleBatchPresence.last_seen_at < cutoff,
        )
    )
    oid = str(user["oid"])
    name = str(user.get("name") or oid)
    row = db.get(ArticleBatchPresence, {"batch_id": batch.id, "user_oid": oid})
    if row is None:
        row = ArticleBatchPresence(
            batch_id=batch.id,
            user_oid=oid,
            user_name=name,
            last_seen_at=now,
        )
        db.add(row)
    else:
        row.user_name = name
        row.last_seen_at = now

    others = list(
        db.scalars(
            select(ArticleBatchPresence).where(
                ArticleBatchPresence.batch_id == batch.id,
                ArticleBatchPresence.user_oid != oid,
                ArticleBatchPresence.last_seen_at >= cutoff,
            )
        )
    )
    return [item.user_name for item in others]


def load_batch_rows(db: Session, batch_id: uuid.UUID) -> list[ArticleBatchRow]:
    return list(
        db.scalars(
            select(ArticleBatchRow)
            .where(ArticleBatchRow.batch_id == batch_id)
            .order_by(ArticleBatchRow.position)
        )
    )
