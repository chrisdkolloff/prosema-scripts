"""Artikelübersicht: group filters and display from Gruppenverwaltung."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.groups_service import list_active_hauptgruppen, list_active_untergruppen
from app.models import ArticleSnapshotRow, Hauptgruppe, Untergruppe

HAUPTGRUPPE_FIELD = "Hauptgruppe"
UNTERGRUPPE_FIELD = "Untergruppe"
_CODE_NAME_SEP = " – "
_LABEL_RE = re.compile(r"^(.*?)\s*-\s*(\d{3})\s*$")


def registry_code_name_label(code: str, name: str) -> str:
    return f"{code}{_CODE_NAME_SEP}{name}"


def registry_pair_label(haupt: Hauptgruppe, unter: Untergruppe) -> str:
    return (
        f"{haupt.code}.{unter.code}{_CODE_NAME_SEP}{haupt.name} / {unter.name}"
    )


@dataclass(frozen=True)
class FilterOption:
    value: str
    label: str


@dataclass
class RegistryLookup:
    haupt_by_code: dict[str, Hauptgruppe]
    unter_by_pair: dict[tuple[str, str], Untergruppe]
    haupt_by_name: dict[str, Hauptgruppe] = field(default_factory=dict)
    unter_by_haupt_code_and_name: dict[tuple[str, str], Untergruppe] = field(
        default_factory=dict
    )


def build_registry_lookup(db: Session) -> RegistryLookup:
    """Prefer active registry rows; fall back to soft-deleted names for legacy numbers."""
    haupt_by_code: dict[str, Hauptgruppe] = {}
    haupt_by_name: dict[str, Hauptgruppe] = {}
    for row in db.scalars(select(Hauptgruppe)):
        existing = haupt_by_code.get(row.code)
        if existing is None or (existing.deleted_at is not None and row.deleted_at is None):
            haupt_by_code[row.code] = row
        name = row.name.strip()
        if name:
            prev = haupt_by_name.get(name)
            if prev is None or (prev.deleted_at is not None and row.deleted_at is None):
                haupt_by_name[name] = row

    unter_by_pair: dict[tuple[str, str], Untergruppe] = {}
    unter_by_haupt_code_and_name: dict[tuple[str, str], Untergruppe] = {}
    stmt = select(Untergruppe, Hauptgruppe).join(
        Hauptgruppe, Untergruppe.hauptgruppe_id == Hauptgruppe.id
    )
    for unter, haupt in db.execute(stmt).all():
        key = (haupt.code, unter.code)
        existing = unter_by_pair.get(key)
        if existing is None or (existing.deleted_at is not None and unter.deleted_at is None):
            unter_by_pair[key] = unter
        uname = unter.name.strip()
        if uname:
            name_key = (haupt.code, uname)
            prev = unter_by_haupt_code_and_name.get(name_key)
            if prev is None or (prev.deleted_at is not None and unter.deleted_at is None):
                unter_by_haupt_code_and_name[name_key] = unter
    return RegistryLookup(
        haupt_by_code=haupt_by_code,
        unter_by_pair=unter_by_pair,
        haupt_by_name=haupt_by_name,
        unter_by_haupt_code_and_name=unter_by_haupt_code_and_name,
    )


def registry_hauptgruppe_filter_options(db: Session) -> list[FilterOption]:
    return [
        FilterOption(
            value=group.code, label=registry_code_name_label(group.code, group.name)
        )
        for group in list_active_hauptgruppen(db)
    ]


def registry_untergruppe_filter_options(
    db: Session, *, hauptgruppe_code: str = ""
) -> list[FilterOption]:
    haupt_code = hauptgruppe_code.strip()
    if haupt_code:
        parent = next(
            (g for g in list_active_hauptgruppen(db) if g.code == haupt_code),
            None,
        )
        if parent is None:
            return []
        return [
            FilterOption(
                value=child.code,
                label=registry_code_name_label(child.code, child.name),
            )
            for child in list_active_untergruppen(db, parent.id)
        ]

    options: list[FilterOption] = []
    for parent in list_active_hauptgruppen(db):
        for child in list_active_untergruppen(db, parent.id):
            value = f"{parent.code}.{child.code}"
            options.append(
                FilterOption(value=value, label=registry_pair_label(parent, child))
            )
    return options


def resolve_filter_group_codes(hauptgruppe: str, untergruppe: str) -> tuple[str, str]:
    """Map URL filter params to Haupt-/Untergruppe registry codes."""
    haupt = hauptgruppe.strip()
    unter = untergruppe.strip()
    if unter and not haupt and "." in unter:
        left, right = unter.split(".", 1)
        if len(left) == 3 and len(right) == 3 and left.isdigit() and right.isdigit():
            return left, right
    return haupt, unter


def _parse_group_label(raw: str) -> tuple[str, str | None]:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return "", None
    match = _LABEL_RE.match(cleaned)
    if match:
        return match.group(1).strip(), match.group(2)
    return cleaned, None


def _resolve_haupt(lookup: RegistryLookup, raw: str) -> Hauptgruppe | None:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return None
    name, code = _parse_group_label(cleaned)
    if code and code in lookup.haupt_by_code:
        return lookup.haupt_by_code[code]
    for needle in (cleaned, name):
        if needle and needle in lookup.haupt_by_name:
            return lookup.haupt_by_name[needle]
    if code and code in lookup.haupt_by_code:
        return lookup.haupt_by_code[code]
    return None


def _resolve_unter(
    lookup: RegistryLookup, haupt: Hauptgruppe | None, raw: str
) -> Untergruppe | None:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return None
    name, code = _parse_group_label(cleaned)
    if haupt is not None:
        if code:
            hit = lookup.unter_by_pair.get((haupt.code, code))
            if hit is not None:
                return hit
        for needle in (cleaned, name):
            if needle:
                hit = lookup.unter_by_haupt_code_and_name.get((haupt.code, needle))
                if hit is not None:
                    return hit
    if code:
        for (haupt_code, unter_code), unter in lookup.unter_by_pair.items():
            if unter_code == code and name in ("", unter.name):
                return unter
    return None


def _assignment_needles(
    lookup: RegistryLookup, *, haupt_code: str, unter_code: str
) -> tuple[set[str], set[str]]:
    haupt_needles: set[str] = set()
    unter_needles: set[str] = set()
    if haupt_code:
        parent = lookup.haupt_by_code.get(haupt_code)
        if parent is not None:
            haupt_needles.update({parent.code, parent.name})
        else:
            haupt_needles.add(haupt_code)
    if unter_code:
        if haupt_code:
            child = lookup.unter_by_pair.get((haupt_code, unter_code))
            if child is not None:
                unter_needles.update({child.code, child.name})
            else:
                unter_needles.add(unter_code)
        else:
            for (hg, ug), child in lookup.unter_by_pair.items():
                if ug == unter_code:
                    unter_needles.update({child.code, child.name})
    return haupt_needles, unter_needles


def count_snapshot_category_assignment(
    db: Session,
    *,
    haupt_code: str,
    unter_code: str = "",
) -> int | None:
    """Articles assigned to this group in the latest snapshot (weclapp category), or None."""
    from app.assistant.catalog import snapshot_for_query

    snapshot = snapshot_for_query(db)
    if snapshot is None:
        return None
    lookup = build_registry_lookup(db)
    haupt_needles, unter_needles = _assignment_needles(
        lookup, haupt_code=haupt_code.strip(), unter_code=unter_code.strip()
    )
    stmt = select(func.count()).where(ArticleSnapshotRow.snapshot_id == snapshot.id)
    if haupt_needles:
        stmt = stmt.where(ArticleSnapshotRow.hauptgruppe_code.in_(haupt_needles))
    if unter_needles:
        stmt = stmt.where(ArticleSnapshotRow.untergruppe_code.in_(unter_needles))
    return int(db.scalar(stmt) or 0)


def apply_registry_group_filters(
    stmt,
    *,
    db: Session,
    hauptgruppe: str,
    untergruppe: str,
):
    """Filter by weclapp category assignment stored on the snapshot row (not article number)."""
    lookup = build_registry_lookup(db)
    haupt_code, unter_code = resolve_filter_group_codes(hauptgruppe, untergruppe)
    haupt_needles, unter_needles = _assignment_needles(
        lookup, haupt_code=haupt_code, unter_code=unter_code
    )
    if haupt_needles:
        stmt = stmt.where(ArticleSnapshotRow.hauptgruppe_code.in_(haupt_needles))
    if unter_needles:
        stmt = stmt.where(ArticleSnapshotRow.untergruppe_code.in_(unter_needles))
    return stmt


def registry_labels_from_weclapp_assignment(
    lookup: RegistryLookup, row: ArticleSnapshotRow
) -> tuple[str | None, str | None]:
    data = row.data if isinstance(row.data, dict) else {}
    haupt_raw = str(data.get(HAUPTGRUPPE_FIELD) or row.hauptgruppe_code or "").strip()
    unter_raw = str(data.get(UNTERGRUPPE_FIELD) or row.untergruppe_code or "").strip()
    haupt = _resolve_haupt(lookup, haupt_raw)
    unter = _resolve_unter(lookup, haupt, unter_raw)
    haupt_label = (
        registry_code_name_label(haupt.code, haupt.name) if haupt is not None else None
    )
    unter_label = (
        registry_code_name_label(unter.code, unter.name) if unter is not None else None
    )
    return haupt_label, unter_label


def row_data_with_registry_groups(
    lookup: RegistryLookup, row: ArticleSnapshotRow
) -> dict[str, str]:
    data = dict(row.data) if isinstance(row.data, dict) else {}
    haupt_label, unter_label = registry_labels_from_weclapp_assignment(lookup, row)
    if haupt_label:
        data[HAUPTGRUPPE_FIELD] = haupt_label
    if unter_label:
        data[UNTERGRUPPE_FIELD] = unter_label
    return data
