"""Global versioned Bezugsquellen upload templates.

Shape follows article_templates (version, is_active, columns jsonb, partial
unique on the active row) with serial PK and no stored xlsx — see module
comments in the 031 migration.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.excel_export import write_cell, write_data_rows, write_header_row
from app.models import (
    Supplier,
    SupplySourceTemplate,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
    WeclappUnit,
)
from app.supply_source_resolve import _prices_for_ss, current_price_row

DEFAULT_COLUMNS: list[dict[str, Any]] = [
    {"key": "supplier_article_number", "label": "Lieferantenartikelnummer", "required": True},
    {"key": "name", "label": "Bezeichnung", "required": False},
    {"key": "listenpreis", "label": "Listenpreis", "required": True},
    {"key": "ean", "label": "EAN", "required": False},
    {"key": "unit", "label": "Einheit", "required": False},
    {"key": "rabattcode", "label": "Rabattcode", "required": False},
    {"key": "min_purchase_qty", "label": "Mindestbestellmenge", "required": False},
    {"key": "procurement_lead_days", "label": "Lieferzeit (Tage)", "required": False},
]

REQUIRED_KEYS = frozenset(c["key"] for c in DEFAULT_COLUMNS if c["required"])
ALL_KEYS = [c["key"] for c in DEFAULT_COLUMNS]
LABEL_BY_KEY = {c["key"]: c["label"] for c in DEFAULT_COLUMNS}
KEY_BY_LABEL = {c["label"]: c["key"] for c in DEFAULT_COLUMNS}

TEXT_COLUMNS = frozenset(
    {
        "Lieferantenartikelnummer",
        "EAN",
        "Einheit",
        "Rabattcode",
        "Bezeichnung",
        "Lieferzeit (Tage)",
    }
)


class SupplySourceTemplateError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def column_spec_from_keys(keys: Sequence[str]) -> list[dict[str, Any]]:
    chosen = set(keys)
    missing = REQUIRED_KEYS - chosen
    if missing:
        labels = [LABEL_BY_KEY[k] for k in ALL_KEYS if k in missing]
        raise SupplySourceTemplateError(
            "Pflichtspalten fehlen: " + ", ".join(labels) + "."
        )
    unknown = chosen - set(ALL_KEYS)
    if unknown:
        raise SupplySourceTemplateError(
            "Unbekannte Spalten: " + ", ".join(sorted(unknown)) + "."
        )
    return [dict(col) for col in DEFAULT_COLUMNS if col["key"] in chosen]


def get_active_template(db: Session) -> SupplySourceTemplate | None:
    return db.scalars(
        select(SupplySourceTemplate).where(SupplySourceTemplate.is_active.is_(True))
    ).first()


def list_templates(db: Session) -> list[SupplySourceTemplate]:
    return list(
        db.scalars(
            select(SupplySourceTemplate).order_by(SupplySourceTemplate.version.desc())
        ).all()
    )


def get_or_create_active_template(
    db: Session,
    *,
    user: Mapping[str, Any],
) -> SupplySourceTemplate:
    existing = get_active_template(db)
    if existing is not None:
        return existing
    return create_template_version(db, keys=ALL_KEYS, user=user, activate=True)


def create_template_version(
    db: Session,
    *,
    keys: Sequence[str],
    user: Mapping[str, Any],
    activate: bool = True,
) -> SupplySourceTemplate:
    columns = column_spec_from_keys(keys)
    next_version = (
        db.scalar(select(func.coalesce(func.max(SupplySourceTemplate.version), 0))) or 0
    ) + 1
    if activate:
        db.execute(
            update(SupplySourceTemplate)
            .where(SupplySourceTemplate.is_active.is_(True))
            .values(is_active=False)
        )
    row = SupplySourceTemplate(
        version=next_version,
        is_active=activate,
        columns=columns,
        created_by=str(user.get("oid") or ""),
        created_by_name=str(user.get("name") or user.get("oid") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def activate_template(db: Session, template: SupplySourceTemplate) -> None:
    db.execute(
        update(SupplySourceTemplate)
        .where(SupplySourceTemplate.is_active.is_(True))
        .values(is_active=False)
    )
    template.is_active = True
    db.commit()


def _unit_name(db: Session, unit_id: str | None, cache: dict[str, str]) -> str:
    if not unit_id:
        return ""
    if unit_id in cache:
        return cache[unit_id]
    unit = db.get(WeclappUnit, unit_id)
    name = unit.name if unit is not None else ""
    cache[unit_id] = name
    return name


def _rabattcode(db: Session, article_ids: list[str], cache: dict[str, str]) -> str:
    codes: list[str] = []
    seen: set[str] = set()
    for aid in article_ids:
        if aid in cache:
            code = cache[aid]
        else:
            article = db.get(WeclappArticle, aid)
            code = (article.rabattcode or "").strip() if article is not None else ""
            cache[aid] = code
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    if not codes:
        return ""
    return codes[0] if len(codes) == 1 else ", ".join(codes)


def generate_template_xlsx_for_user(
    db: Session,
    supplier: Supplier,
    *,
    user: Mapping[str, Any],
) -> tuple[SupplySourceTemplate, bytes]:
    template = get_or_create_active_template(db, user=user)
    columns = template.columns if isinstance(template.columns, list) else DEFAULT_COLUMNS
    headers = [str(col.get("label") or "") for col in columns]
    keys = [str(col.get("key") or "") for col in columns]

    sources = list(
        db.scalars(
            select(WeclappSupplySource).where(
                WeclappSupplySource.supplier_party_id == supplier.weclapp_party_id,
                WeclappSupplySource.missing_since.is_(None),
            )
        ).all()
    )
    links_by_ss: dict[str, list[str]] = {}
    if sources:
        ss_ids = [s.weclapp_id for s in sources]
        for link in db.scalars(
            select(WeclappSupplySourceLink).where(
                WeclappSupplySourceLink.supply_source_weclapp_id.in_(ss_ids)
            )
        ):
            links_by_ss.setdefault(link.supply_source_weclapp_id, []).append(
                link.weclapp_article_id
            )

    unit_cache: dict[str, str] = {}
    code_cache: dict[str, str] = {}
    rows: list[dict[str, object]] = []
    for ss in sources:
        price = current_price_row(_prices_for_ss(db, ss.weclapp_id))
        values = {
            "supplier_article_number": ss.supplier_article_number or "",
            "name": ss.name or "",
            "listenpreis": price.price if price is not None else "",
            "ean": ss.ean or "",
            "unit": _unit_name(db, ss.unit_id, unit_cache),
            "rabattcode": _rabattcode(db, links_by_ss.get(ss.weclapp_id, []), code_cache),
            "min_purchase_qty": ss.min_purchase_qty if ss.min_purchase_qty is not None else "",
            "procurement_lead_days": (
                ss.procurement_lead_days if ss.procurement_lead_days is not None else ""
            ),
        }
        rows.append({LABEL_BY_KEY[k]: values.get(k, "") for k in keys if k in LABEL_BY_KEY})

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Bezugsquellen"
    write_header_row(ws, headers)
    if rows:
        write_data_rows(ws, headers, rows, text_columns=TEXT_COLUMNS)
    else:
        for col_idx, header in enumerate(headers, start=1):
            write_cell(ws.cell(row=2, column=col_idx), header, "", text_columns=TEXT_COLUMNS)

    buf = io.BytesIO()
    wb.save(buf)
    return template, buf.getvalue()
