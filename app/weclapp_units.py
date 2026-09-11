"""weclapp unit catalogue for the supply-source grid.

Live probe 2026-09-04 on supply source 353019 (article 999.999.001 only):
PUT ``unitId`` 3566 → 4259 with ignoreMissingProperties returned 400
``unit cannot be changed``. The article ``unitId`` stayed 3566. Version did not
bump. Changing unit on an existing supply source is not writable.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SupplierUnitAlias, WeclappArticle, WeclappUnit

# See module docstring. Do not send unitId on PUT of an existing supply source.
UNIT_ID_PUT_WRITABLE = False

UNIT_LOCKED_HINT = (
    "Einheit einer bestehenden Bezugsquelle. weclapp lässt sie nach dem Anlegen "
    "nicht mehr ändern."
)

UNIT_LOCKED_ERROR = (
    "Einheit einer bestehenden Bezugsquelle lässt sich nicht ändern — weclapp lehnt das ab. "
    "Nur bei «neu anlegen» und «zuordnen» ist die Einheit editierbar."
)

UNIT_OVERWRITE_HINT = (
    "Datei-Einheit weicht von der Artikel- bzw. Bezugsquellen-Einheit ab. "
    "Die weclapp-Einheit bleibt massgebend."
)


def fold_unit_word(value: str) -> str:
    return (value or "").strip().casefold()


def catalogue_unit_id(units: list[WeclappUnit], raw: str) -> str | None:
    """Unique match on folded name or description. Ambiguous → None."""
    key = fold_unit_word(raw)
    if not key:
        return None
    hits: dict[str, str] = {}
    for unit in units:
        for label in (unit.name, unit.description):
            folded = fold_unit_word(label or "")
            if folded != key:
                continue
            hits[unit.weclapp_id] = unit.weclapp_id
    if len(hits) == 1:
        return next(iter(hits))
    return None


def alias_unit_id(db: Session, *, supplier_id: int | None, raw: str) -> str | None:
    if supplier_id is None:
        return None
    key = fold_unit_word(raw)
    if not key:
        return None
    row = db.scalars(
        select(SupplierUnitAlias).where(
            SupplierUnitAlias.supplier_id == supplier_id,
            SupplierUnitAlias.word_key == key,
        )
    ).first()
    if row is None:
        return None
    uid = (row.unit_id or "").strip()
    return uid or None


def resolve_upload_unit(
    db: Session,
    raw: str | None,
    *,
    supplier_id: int | None,
    units: list[WeclappUnit] | None = None,
) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    catalogue = units if units is not None else list(db.scalars(select(WeclappUnit)).all())
    matched = catalogue_unit_id(catalogue, text)
    if matched:
        return matched
    return alias_unit_id(db, supplier_id=supplier_id, raw=text)


def units_as_lookup_dicts(db: Session) -> list[dict[str, str]]:
    """Catalogue rows as LookupTables unit dicts (id/name/description).

    Empty when the mirror has not been indexed yet — callers keep schema JSON.
    """
    rows = list(db.scalars(select(WeclappUnit)).all())
    return [
        {
            "id": u.weclapp_id,
            "name": u.name or "",
            "description": u.description or "",
        }
        for u in rows
        if (u.weclapp_id or "").strip()
    ]


def units_for_dropdown(db: Session) -> list[dict[str, str]]:
    """All catalogue units, usage-desc so unused names fall to the bottom."""
    counts = dict(
        db.execute(
            select(WeclappArticle.unit_id, func.count())
            .where(WeclappArticle.unit_id.is_not(None))
            .where(WeclappArticle.missing_since.is_(None))
            .group_by(WeclappArticle.unit_id)
        ).all()
    )
    rows = [u for u in db.scalars(select(WeclappUnit)).all() if (u.name or "").strip()]
    rows.sort(
        key=lambda u: (-int(counts.get(u.weclapp_id) or 0), (u.name or "").casefold())
    )
    return [
        {
            "id": u.weclapp_id,
            "name": u.name,
            "description": u.description or "",
        }
        for u in rows
    ]
