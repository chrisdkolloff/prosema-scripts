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
from app.numbering_high_water import register_kept_numbers, seed_high_water
from core.article_fields import IMPORT_COLUMNS, grid_display_title
from core.article_payload import (
    ARTICLE_NAME_FIELD,
    ARTICLE_NUMBER_FIELD,
    DEFAULTS,
    LONG_TEXT_FIELD,
    NUMBER_PLACEHOLDER,
    get_row_value,
    label_variants,
    row_to_payload,
)
from core.numbering import Scheme
from scripts.weclapp.article_import import (
    RESTRICTED_SELECT_COLUMNS,
    LookupTables,
    dropdown_options,
)

JSPREADSHEET_CE_VERSION = "5.0.4"
JSUITES_VERSION = "5.13.5"

GRID_PAGE_SIZE = 250
PRESENCE_TTL = timedelta(seconds=20)
FLUSH_IDLE_MS = 400

MSG_FIELD_NOT_EDITABLE = "Feld nicht bearbeitbar"
MSG_BATCH_APPROVED = "Stapel bereits genehmigt — keine Änderungen möglich"
MSG_NUMBER_REASSIGNED = "Artikelnummer wurde neu vergeben."
MSG_UNKNOWN_HAUPT = "Unbekannte Hauptgruppe"
MSG_UNKNOWN_UNTER = "Unbekannte Untergruppe"
MSG_MISSING_HAUPT = "Hauptgruppe fehlt"
MSG_MISSING_UNTER = "Untergruppe fehlt"

INCLUDE_FIELD = "include"
KURZTEXT_FIELD = ARTICLE_NAME_FIELD
HAUPTGRUPPE_FIELD = "Hauptgruppe"
UNTERGRUPPE_FIELD = "Untergruppe"
GROUP_FIELDS = {HAUPTGRUPPE_FIELD, UNTERGRUPPE_FIELD}

_NUMBER_KEYS = frozenset(label_variants(ARTICLE_NUMBER_FIELD))
_NAME_KEYS = frozenset(label_variants(ARTICLE_NAME_FIELD))
_PINNED_KEYS = _NUMBER_KEYS | _NAME_KEYS

NEVER_EDITABLE = {
    *label_variants(ARTICLE_NUMBER_FIELD),
    "Produkt-ID (Prosema)",
    "Varianten-ID (Prosema)",
}

EDITABLE_WHITELIST: frozenset[str] = frozenset(
    {
        *(column for column in IMPORT_COLUMNS if column not in NEVER_EDITABLE),
        *(
            alias
            for column in IMPORT_COLUMNS
            if column not in NEVER_EDITABLE
            for alias in label_variants(column)
        ),
        INCLUDE_FIELD,
    }
)

SYNTHETIC_FIELDS = ("_zeile", "_status")

_LABEL_RE = re.compile(r"^(.*?)\s*-\s*(\d{3})\s*$")

COLUMN_WIDTHS: dict[str, int] = {
    "_zeile": 70,
    ARTICLE_NUMBER_FIELD: 160,
    "Prosema Artikelnummer": 160,
    KURZTEXT_FIELD: 220,
    "PROSEMA Kurztext": 220,
    "_status": 280,
    INCLUDE_FIELD: 100,
    "Lieferantenartikelnummer": 180,
    HAUPTGRUPPE_FIELD: 190,
    UNTERGRUPPE_FIELD: 210,
    LONG_TEXT_FIELD: 280,
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


def grid_field_order_for_batch(batch: ArticleBatch) -> tuple[str, ...]:
    """Grid columns follow the batch's pinned template; fallback is the catalogue."""
    template = getattr(batch, "template", None)
    columns = template.columns if template is not None else None
    if not isinstance(columns, list) or not columns:
        return GRID_FIELD_ORDER
    labels = [
        str(col.get("key") or col.get("label") or "")
        for col in columns
        if col.get("key") or col.get("label")
    ]
    # Always show number + Kurztext near the front even if template order differs.
    body = [label for label in labels if label and label not in _PINNED_KEYS]
    number_label = next((label for label in labels if label in _NUMBER_KEYS), ARTICLE_NUMBER_FIELD)
    name_label = next((label for label in labels if label in _NAME_KEYS), None)
    ordered: list[str] = ["_zeile", number_label]
    if name_label:
        ordered.append(name_label)
    ordered.append("_status")
    ordered.append(INCLUDE_FIELD)
    ordered.extend(body)
    return tuple(ordered)


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
    number_reassigned: bool = False


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


def _lookup_aliased(data: dict[str, Any], column: str) -> str | None:
    for key in label_variants(column):
        if key in data:
            return _as_text(data[key])
    return None


def effective_values(row: ArticleBatchRow) -> dict[str, str]:
    merged: dict[str, str] = {}
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    edits = row.edits if isinstance(row.edits, dict) else {}
    for column in IMPORT_COLUMNS:
        edited = _lookup_aliased(edits, column)
        if edited is not None:
            merged[column] = edited
            continue
        original = _lookup_aliased(raw, column)
        if original is not None:
            merged[column] = original
        else:
            merged[column] = DEFAULTS.get(column, "")
    merged[ARTICLE_NUMBER_FIELD] = row.proposed_article_number or merged.get(
        ARTICLE_NUMBER_FIELD, ""
    )
    return merged


def display_proposed_article_number(row: ArticleBatchRow) -> str:
    """Grid/API display value — pending numbers show the placeholder, not blank."""
    number = (row.proposed_article_number or "").strip()
    if number:
        return number
    return NUMBER_PLACEHOLDER


_LOOKUPS: LookupTables | None = None
_DROPDOWN_CACHE: dict[str, list[str]] | None = None


def _cached_lookups() -> LookupTables:
    global _LOOKUPS
    if _LOOKUPS is None:
        from scripts.weclapp.article_import import _load_schema

        _LOOKUPS = LookupTables(_load_schema())
    return _LOOKUPS


def schema_dropdowns() -> dict[str, list[str]]:
    """weclapp schema dropdowns — never Hauptgruppe/Untergruppe.

    Those columns are filled by ``group_dropdowns`` from Gruppenverwaltung.
    """
    global _DROPDOWN_CACHE
    if _DROPDOWN_CACHE is None:
        options = dropdown_options(_cached_lookups())
        options.pop(HAUPTGRUPPE_FIELD, None)
        options.pop(UNTERGRUPPE_FIELD, None)
        _DROPDOWN_CACHE = options
    return _DROPDOWN_CACHE


def group_dropdowns(db: Session) -> tuple[list[str], dict[str, list[str]]]:
    """Active Hauptgruppe labels and Untergruppe labels keyed by parent label."""
    haupt: list[str] = []
    unter_by_haupt: dict[str, list[str]] = {}
    for group in list_active_hauptgruppen(db):
        label = group_label(group.name, group.code)
        haupt.append(label)
        unter_by_haupt[label] = [
            group_label(child.name, child.code)
            for child in list_active_untergruppen(db, group.id)
        ]
    return haupt, unter_by_haupt


def _flat_untergruppe_labels(unter_by_haupt: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    flat: list[str] = []
    for children in unter_by_haupt.values():
        for label in children:
            if label not in seen:
                seen.add(label)
                flat.append(label)
    return flat


def build_columns(
    db: Session,
    *,
    editable: bool,
    field_order: tuple[str, ...] | None = None,
    group_sources: tuple[list[str], dict[str, list[str]]] | None = None,
) -> list[dict[str, Any]]:
    schema_sources = schema_dropdowns()
    if group_sources is None:
        haupt, unter_by_haupt = group_dropdowns(db)
    else:
        haupt, unter_by_haupt = group_sources
    sources = {
        **schema_sources,
        HAUPTGRUPPE_FIELD: haupt,
        UNTERGRUPPE_FIELD: _flat_untergruppe_labels(unter_by_haupt),
    }
    order = field_order if field_order is not None else GRID_FIELD_ORDER
    columns: list[dict[str, Any]] = []
    for field_name in order:
        read_only = (
            (not editable)
            or field_name in SYNTHETIC_FIELDS
            or field_name not in EDITABLE_WHITELIST
        )
        column: dict[str, Any] = {
            "type": "text",
            "title": COLUMN_TITLES.get(field_name) or grid_display_title(field_name),
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


def grid_row_values(
    row: ArticleBatchRow,
    *,
    field_order: tuple[str, ...] | None = None,
) -> list[Any]:
    values = effective_values(row)
    order = field_order if field_order is not None else GRID_FIELD_ORDER
    out: list[Any] = []
    for field_name in order:
        if field_name == "_zeile":
            out.append(row.position)
        elif field_name == "_status":
            out.append(row.validation_error or "")
        elif field_name == INCLUDE_FIELD:
            out.append(bool(row.include))
        elif field_name in _NUMBER_KEYS:
            out.append(display_proposed_article_number(row))
        else:
            out.append(get_row_value(values, field_name) or values.get(field_name, ""))
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


def recompute_row_validation(db: Session, row: ArticleBatchRow) -> bool:
    """Refresh stored group resolution and validation from Gruppenverwaltung."""
    values = effective_values(row)
    haupt, unter, group_error = resolve_row_groups(db, values)
    row.resolved_hauptgruppe_id = haupt.id if haupt is not None else None
    row.resolved_untergruppe_id = unter.id if unter is not None else None
    error = validate_effective(values, group_error)
    if (row.validation_error or "") != (error or ""):
        row.validation_error = error
        return True
    return False


def refresh_draft_validation(
    db: Session, batch: ArticleBatch, rows: list[ArticleBatchRow]
) -> bool:
    """Recompute validation on a draft so stale weclapp-list errors do not linger."""
    if batch.status != "draft":
        return False
    changed = False
    for row in rows:
        if recompute_row_validation(db, row):
            changed = True
    return changed


def _number_matches(number: str, main: str, sub: str) -> bool:
    match = Scheme().pattern().match((number or "").strip())
    return bool(match and match.group(1) == main and match.group(2) == sub)


def _assign_numbers(
    db: Session,
    batch: ArticleBatch,
    rows: list[ArticleBatchRow],
    affected_ids: set[uuid.UUID],
) -> set[uuid.UUID]:
    scheme = Scheme()
    need_new: list[ArticleBatchRow] = []
    reassigned: set[uuid.UUID] = set()
    reserved = seed_high_water(db, exclude_batch_id=batch.id)
    register_kept_numbers(rows, reserved, skip_ids=affected_ids)

    for row in rows:
        if row.id not in affected_ids:
            continue
        existing = (row.proposed_article_number or "").strip()
        haupt = getattr(row, "_resolved_haupt", None)
        unter = getattr(row, "_resolved_unter", None)
        if haupt is None or unter is None:
            if existing:
                row.proposed_article_number = ""
                reassigned.add(row.id)
            continue
        if _number_matches(existing, haupt.code, unter.code):
            key = (haupt.code, unter.code)
            match = scheme.pattern().match(existing)
            if match:
                reserved[key] = max(reserved.get(key, 0), int(match.group(3)))
            continue
        need_new.append(row)

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
        new_number = scheme.format(haupt.code, unter.code, nxt)
        if new_number != (row.proposed_article_number or ""):
            reassigned.add(row.id)
        row.proposed_article_number = new_number
    return reassigned


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
    edited_fields: dict[uuid.UUID, set[str]] = {}
    for edit in edits:
        row = by_id.get(edit.row_id)
        if row is None:
            raise BatchEditError("Zeile gehört nicht zu diesem Stapel", field=edit.field)
        affected[row.id] = row
        edited_fields.setdefault(row.id, set()).add(edit.field)

    for edit in edits:
        _write_edit(by_id[edit.row_id], edit.field, edit.value)

    cleared_unter: set[uuid.UUID] = set()
    for row in affected.values():
        values = effective_values(row)
        haupt, unter, group_error = resolve_row_groups(db, values)
        # Changing Hauptgruppe invalidates a foreign Untergruppe — clear it.
        if (
            HAUPTGRUPPE_FIELD in edited_fields.get(row.id, set())
            and UNTERGRUPPE_FIELD not in edited_fields.get(row.id, set())
            and haupt is not None
            and unter is None
            and (values.get(UNTERGRUPPE_FIELD) or "").strip()
        ):
            _write_edit(row, UNTERGRUPPE_FIELD, "")
            cleared_unter.add(row.id)
            values = effective_values(row)
            haupt, unter, group_error = resolve_row_groups(db, values)
        row._resolved_haupt = haupt
        row._resolved_unter = unter
        row._group_error = group_error
        row.resolved_hauptgruppe_id = haupt.id if haupt is not None else None
        row.resolved_untergruppe_id = unter.id if unter is not None else None

    reassigned = _assign_numbers(db, batch, rows, set(affected))

    results: list[RowEditResult] = []
    for row in affected.values():
        corrected = _canonical_group_edits(row)
        if row.id in cleared_unter:
            corrected[UNTERGRUPPE_FIELD] = ""
        values = effective_values(row)
        row.validation_error = validate_effective(values, getattr(row, "_group_error", None))
        results.append(
            RowEditResult(
                id=row.id,
                proposed_article_number=display_proposed_article_number(row),
                validation_error=row.validation_error or "",
                include=bool(row.include),
                corrected=corrected,
                number_reassigned=row.id in reassigned,
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
                get_row_value(values, ARTICLE_NUMBER_FIELD),
                values.get("Lieferantenartikelnummer", ""),
                get_row_value(values, KURZTEXT_FIELD),
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
    field_order = grid_field_order_for_batch(batch)
    group_sources = group_dropdowns(db)
    _haupt, unter_by_haupt = group_sources
    return {
        "editsUrl": f"/batches/{batch.id}/edits",
        "actionsUrl": f"/batches/{batch.id}/aktionen",
        "editable": editable,
        "parseFormulas": False,
        "freezeColumns": 3,
        "idleMs": FLUSH_IDLE_MS,
        "columns": build_columns(
            db,
            editable=editable,
            field_order=field_order,
            group_sources=group_sources,
        ),
        "data": [grid_row_values(row, field_order=field_order) for row in rows],
        "rowIds": [str(row.id) for row in rows],
        "rowState": [
            {
                "validation_error": row.validation_error or "",
                "include": bool(row.include),
            }
            for row in rows
        ],
        "fields": list(field_order),
        # Client filter: Untergruppe dropdown options per Hauptgruppe label.
        "untergruppeByHauptgruppe": unter_by_haupt,
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
