"""Create, edit, price, and approve supply-source resolve runs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Supplier,
    SupplierArticleAlias,
    SupplySourceRow,
    SupplySourceRun,
    WeclappArticle,
)
from app.supply_source_resolve import resolve_row

ZERO = Decimal(0)
ONE = Decimal(1)

INTENT_LABELS = {
    "update": "aktualisieren",
    "price_only": "nur Preisänderung",
    "create": "neu anlegen",
    "attach": "zuordnen",
    "renumber": "neue Lieferantennummer",
    "skip": "auslassen",
}

EDITABLE_STATUSES = frozenset({"preview"})
BUSY_STATUSES = frozenset({"running", "applying"})


class SupplySourceRunError(ValueError):
    pass


def _d(value: Decimal | None) -> Decimal | None:
    return value if value is None else Decimal(value)


def parse_rate(raw: object) -> Decimal | None:
    """Accept a fraction (< 1) or percent points (>= 1). Blank is None, not zero."""
    if raw is None:
        return None
    text = str(raw).strip().replace("%", "").replace(" ", "").replace(",", ".")
    if text == "":
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise SupplySourceRunError("Rabattsatz ist keine Zahl.") from exc
    if value >= 1:
        value = value / Decimal(100)
    if value < 0 or value >= 1:
        raise SupplySourceRunError("Rabattsatz muss zwischen 0 % und 100 % liegen.")
    return value


def parse_money(raw: object) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace("'", "").replace(" ", "").replace(",", ".")
    if text == "":
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise SupplySourceRunError("Betrag ist keine Zahl.") from exc
    if value < 0:
        raise SupplySourceRunError("Betrag darf nicht negativ sein.")
    return value


def derived_prices(
    row: SupplySourceRow, run: SupplySourceRun
) -> dict[str, Decimal | None]:
    listen = _d(row.listenpreis)
    r1 = _d(row.rabatt_1) if row.discount_set else None
    r2 = _d(row.rabatt_2) if row.discount_set else None
    ek = None
    if listen is not None and row.discount_set:
        factor1 = ONE - (r1 if r1 is not None else ZERO)
        factor2 = ONE - (r2 if r2 is not None else ZERO)
        ek = listen * factor1 * factor2
    kurs = _d(run.kurs) or ONE
    if run.einkaufswaehrung == "CHF":
        kurs = ONE
    ek_chf = ek * kurs if ek is not None else None
    if row.vk_override is not None:
        vk = _d(row.vk_override)
    elif ek_chf is not None:
        vk = ek_chf * (ONE + (_d(run.aufschlag) or ZERO))
    else:
        vk = None
    marge = None
    if vk is not None and ek_chf is not None and vk != 0:
        marge = (vk - ek_chf) / vk
    implied = None
    current = _d(row.current_ek)
    if listen is not None and current is not None and listen != 0:
        implied = ONE - (current / listen)
    return {
        "ek": ek,
        "ek_chf": ek_chf,
        "vk_chf": vk,
        "marge": marge,
        "implied_discount": implied,
    }


def format_swiss_number(value: Decimal | int | None, *, places: int = 2) -> str:
    if value is None:
        return ""
    quantized = Decimal(value).quantize(Decimal(1).scaleb(-places))
    sign, digits, exp = quantized.as_tuple()
    padded = "".join(str(d) for d in digits)
    if exp >= 0:
        intpart = padded + ("0" * exp)
        frac = ""
    else:
        if len(padded) <= -exp:
            padded = padded.zfill(-exp + 1)
        intpart = padded[:exp] or "0"
        frac = padded[exp:]
    groups: list[str] = []
    while intpart:
        groups.append(intpart[-3:])
        intpart = intpart[:-3]
    grouped = "'".join(reversed(groups))
    prefix = "-" if sign else ""
    if places:
        return f"{prefix}{grouped}.{frac}"
    return f"{prefix}{grouped}"


def format_pct(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format_swiss_number(value * Decimal(100), places=2)


def running_for_supplier(db: Session, supplier_id: int) -> SupplySourceRun | None:
    return db.scalars(
        select(SupplySourceRun).where(
            SupplySourceRun.supplier_id == supplier_id,
            SupplySourceRun.status.in_(tuple(BUSY_STATUSES)),
        )
    ).first()


def list_runs(db: Session, *, supplier_id: int | None = None) -> list[SupplySourceRun]:
    stmt = select(SupplySourceRun).options(joinedload(SupplySourceRun.supplier))
    if supplier_id is not None:
        stmt = stmt.where(SupplySourceRun.supplier_id == supplier_id)
    stmt = stmt.order_by(SupplySourceRun.created_at.desc())
    return list(db.scalars(stmt).unique().all())


def list_suppliers(db: Session) -> list[Supplier]:
    return list(
        db.scalars(
            select(Supplier)
            .where(Supplier.deleted_at.is_(None), Supplier.is_active.is_(True))
            .order_by(Supplier.supplier_number)
        ).all()
    )


def create_pull_run(
    db: Session,
    *,
    supplier_id: int,
    user: Mapping[str, Any],
) -> SupplySourceRun:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None or supplier.deleted_at is not None:
        raise SupplySourceRunError("Lieferant nicht gefunden.")
    if running_for_supplier(db, supplier.id) is not None:
        raise SupplySourceRunError("Für diesen Lieferanten läuft bereits ein Abgleich.")
    kurs = supplier.default_kurs
    if supplier.einkaufswaehrung == "CHF":
        kurs = Decimal("1.0")
    run = SupplySourceRun(
        supplier_id=supplier.id,
        status="running",
        source="pull",
        einkaufswaehrung=supplier.einkaufswaehrung,
        kurs=kurs,
        verkaufswaehrung=supplier.default_verkaufswaehrung,
        aufschlag=supplier.default_aufschlag,
        created_by=str(user["oid"]),
        created_by_name=str(user.get("name") or user["oid"]),
    )
    db.add(run)
    db.flush()
    from app.jobs import enqueue

    job = enqueue(
        db,
        "supply_source_resolve",
        {"run_id": run.id},
        user,
    )
    run.job_id = job.id
    db.commit()
    db.refresh(run)
    return run


def summary_counts(rows: list[SupplySourceRow]) -> dict[str, int]:
    return {
        "update": sum(1 for r in rows if r.row_intent == "update"),
        "price_only": sum(1 for r in rows if r.row_intent == "price_only"),
        "create": sum(1 for r in rows if r.row_intent == "create"),
        "renumber": sum(1 for r in rows if r.row_intent == "renumber"),
        "unmatched": sum(
            1
            for r in rows
            if r.match_status == "unmatched" and r.row_intent != "skip"
        ),
        "discount_unset": sum(
            1
            for r in rows
            if not r.discount_set and r.row_intent != "skip"
        ),
        "skip": sum(1 for r in rows if r.row_intent == "skip"),
        "total": len(rows),
        "attach": sum(1 for r in rows if r.row_intent == "attach"),
    }


def approval_blockers(rows: list[SupplySourceRow]) -> dict[str, int]:
    unmatched = 0
    unset = 0
    for row in rows:
        if row.row_intent == "skip":
            continue
        if row.match_status == "unmatched":
            unmatched += 1
        if not row.discount_set:
            unset += 1
    return {"unmatched": unmatched, "discount_unset": unset}


def can_approve(rows: list[SupplySourceRow]) -> bool:
    blocks = approval_blockers(rows)
    return blocks["unmatched"] == 0 and blocks["discount_unset"] == 0


def load_rows(db: Session, run_id: int) -> list[SupplySourceRow]:
    return list(
        db.scalars(
            select(SupplySourceRow)
            .where(SupplySourceRow.run_id == run_id)
            .order_by(SupplySourceRow.supplier_article_number)
        ).all()
    )


def assert_editable(run: SupplySourceRun) -> None:
    if run.status not in EDITABLE_STATUSES:
        raise SupplySourceRunError("Dieser Lauf lässt sich nicht mehr ändern.")


def set_rates(
    row: SupplySourceRow,
    *,
    rabatt_1: Decimal | None,
    rabatt_2: Decimal | None,
    kein_rabatt: bool = False,
) -> None:
    if kein_rabatt:
        row.rabatt_1 = ZERO
        row.rabatt_2 = ZERO
        row.discount_set = True
        row.discount_source = "manual"
        return
    if rabatt_1 is None and rabatt_2 is None:
        row.rabatt_1 = None
        row.rabatt_2 = None
        row.discount_set = False
        row.discount_source = None
        return
    row.rabatt_1 = rabatt_1 if rabatt_1 is not None else ZERO
    row.rabatt_2 = rabatt_2 if rabatt_2 is not None else ZERO
    row.discount_set = True
    row.discount_source = "manual"


def apply_bulk_rates(
    db: Session,
    run: SupplySourceRun,
    *,
    row_ids: list[int] | None = None,
    rabattcode: str | None = None,
    rabatt_1: Decimal | None = None,
    rabatt_2: Decimal | None = None,
    kein_rabatt: bool = False,
) -> int:
    assert_editable(run)
    if not row_ids and rabattcode is None:
        raise SupplySourceRunError("Keine Zeilen ausgewählt.")
    stmt = select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
    if row_ids:
        stmt = stmt.where(SupplySourceRow.id.in_(row_ids))
    elif rabattcode is not None:
        stmt = stmt.where(SupplySourceRow.rabattcode == rabattcode)
    rows = list(db.scalars(stmt).all())
    for row in rows:
        set_rates(row, rabatt_1=rabatt_1, rabatt_2=rabatt_2, kein_rabatt=kein_rabatt)
    db.commit()
    return len(rows)


def apply_edits(
    db: Session,
    run: SupplySourceRun,
    edits: list[dict[str, Any]],
) -> list[SupplySourceRow]:
    assert_editable(run)
    by_id = {
        row.id: row
        for row in db.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        ).all()
    }
    touched: list[SupplySourceRow] = []
    for edit in edits:
        row = by_id.get(int(edit["row_id"]))
        if row is None:
            continue
        field = str(edit.get("field") or "")
        value = edit.get("value")
        if field in {"rabatt_1", "rabatt_2"}:
            rate = parse_rate(value)
            if field == "rabatt_1":
                set_rates(
                    row,
                    rabatt_1=rate,
                    rabatt_2=row.rabatt_2 if row.discount_set else rate,
                )
            else:
                set_rates(
                    row,
                    rabatt_1=row.rabatt_1 if row.discount_set else ZERO,
                    rabatt_2=rate,
                )
        elif field in {"vk_override", "vk_chf"}:
            row.vk_override = parse_money(value)
        elif field == "row_intent":
            intent = str(value or "").strip()
            if intent == "skip":
                row.row_intent = "skip"
            elif intent in INTENT_LABELS and intent != "skip":
                row.row_intent = intent
        else:
            continue
        touched.append(row)
    db.commit()
    return touched


def apply_run_settings(
    db: Session,
    run: SupplySourceRun,
    *,
    einkaufswaehrung: str,
    kurs: Decimal,
    verkaufswaehrung: str,
    aufschlag: Decimal,
    preis_eintritt: datetime | None,
) -> None:
    assert_editable(run)
    if einkaufswaehrung not in {"EUR", "CHF"}:
        raise SupplySourceRunError("Einkaufswährung ist ungültig.")
    if verkaufswaehrung not in {"EUR", "CHF"}:
        raise SupplySourceRunError("Verkaufswährung ist ungültig.")
    if kurs <= 0:
        raise SupplySourceRunError("Kurs muss grösser als 0 sein.")
    if einkaufswaehrung == "CHF":
        kurs = Decimal("1.0")
    if aufschlag < 0:
        raise SupplySourceRunError("Aufschlag darf nicht negativ sein.")
    run.einkaufswaehrung = einkaufswaehrung
    run.kurs = kurs
    run.verkaufswaehrung = verkaufswaehrung
    run.aufschlag = aufschlag
    run.preis_eintritt = preis_eintritt
    db.commit()


def attach_manual_alias(
    db: Session,
    run: SupplySourceRun,
    row: SupplySourceRow,
    *,
    article_number: str,
    oid: str,
    name: str = "",
) -> SupplierArticleAlias:
    assert_editable(run)
    number = article_number.strip()
    if not number:
        raise SupplySourceRunError("Artikelnummer fehlt.")
    article = db.scalars(
        select(WeclappArticle).where(WeclappArticle.article_number == number)
    ).first()
    if article is None:
        raise SupplySourceRunError("Artikel in weclapp nicht gefunden.")
    existing = db.scalars(
        select(SupplierArticleAlias).where(
            SupplierArticleAlias.supplier_id == run.supplier_id,
            SupplierArticleAlias.supplier_article_number == row.supplier_article_number,
            SupplierArticleAlias.article_number == number,
        )
    ).first()
    if existing is None:
        existing = SupplierArticleAlias(
            supplier_id=run.supplier_id,
            supplier_article_number=row.supplier_article_number,
            article_number=number,
            weclapp_article_id=article.weclapp_article_id,
            source="manual",
            confirmed_by=oid,
            confirmed_at=datetime.now(UTC),
        )
        db.add(existing)
    else:
        existing.source = "manual"
        existing.confirmed_by = oid
        existing.confirmed_at = datetime.now(UTC)
    supplier = db.get(Supplier, run.supplier_id)
    if supplier is None:
        raise SupplySourceRunError("Lieferant nicht gefunden.")
    resolve_row(db, run, row, supplier=supplier)
    db.commit()
    return existing


def approve_run(db: Session, run: SupplySourceRun) -> None:
    assert_editable(run)
    rows = load_rows(db, run.id)
    if not can_approve(rows):
        raise SupplySourceRunError(
            "Freigabe nicht möglich: offene Zuordnungen oder fehlende Rabattsätze."
        )
    run.status = "approved"
    db.commit()


def row_payload(row: SupplySourceRow, run: SupplySourceRun) -> dict[str, Any]:
    prices = derived_prices(row, run)
    numbers = list(row.resolved_article_numbers or [])
    return {
        "id": row.id,
        "supplier_article_number": row.supplier_article_number,
        "name": row.name or "",
        "article_numbers": numbers,
        "article_numbers_label": ", ".join(numbers),
        "multi_article": len(numbers) > 1,
        "rabattcode": row.rabattcode or "",
        "listenpreis": row.listenpreis,
        "rabatt_1": row.rabatt_1,
        "rabatt_2": row.rabatt_2,
        "discount_set": row.discount_set,
        "ek": prices["ek"],
        "ek_chf": prices["ek_chf"],
        "vk_chf": prices["vk_chf"],
        "marge": prices["marge"],
        "vk_override": row.vk_override,
        "current_ek": row.current_ek,
        "implied_discount": prices["implied_discount"],
        "match_status": row.match_status,
        "match_tier": row.match_tier,
        "row_intent": row.row_intent or "",
        "intent_label": INTENT_LABELS.get(row.row_intent or "", ""),
    }


def build_grid_config(run: SupplySourceRun, rows: list[SupplySourceRow]) -> dict[str, Any]:
    payloads = [row_payload(row, run) for row in rows]
    fields = [
        "supplier_article_number",
        "name",
        "article_numbers_label",
        "rabattcode",
        "listenpreis",
        "rabatt_1",
        "rabatt_2",
        "ek",
        "ek_chf",
        "vk_chf",
        "marge",
        "current_ek",
        "implied_discount",
        "match_status",
        "row_intent",
    ]
    columns = [
        {"title": "Lieferantenartikelnummer", "width": 160, "readOnly": True},
        {"title": "Bezeichnung", "width": 280, "readOnly": True},
        {"title": "PROSEMA-Artikelnummer(n)", "width": 180, "readOnly": True},
        {"title": "Rabattcode", "width": 110, "readOnly": True},
        {"title": "Listenpreis", "width": 110, "readOnly": True},
        {"title": "Rabatt 1", "width": 90},
        {"title": "Rabatt 2", "width": 90},
        {"title": "EK", "width": 100, "readOnly": True},
        {"title": "EK CHF", "width": 100, "readOnly": True},
        {"title": "VK CHF", "width": 110},
        {"title": "Marge %", "width": 90, "readOnly": True},
        {"title": "Aktueller EK", "width": 110, "readOnly": True},
        {"title": "Impliziter Rabatt", "width": 130, "readOnly": True},
        {"title": "Zuordnung", "width": 120, "readOnly": True},
        {
            "title": "Vorgang",
            "width": 180,
            "type": "dropdown",
            "source": [
                ["update", "aktualisieren"],
                ["price_only", "nur Preisänderung"],
                ["create", "neu anlegen"],
                ["attach", "zuordnen"],
                ["renumber", "neue Lieferantennummer"],
                ["skip", "auslassen"],
            ],
        },
    ]
    data = []
    unmatched_rows: list[int] = []
    for i, payload in enumerate(payloads):
        r1 = (
            format_pct(payload["rabatt_1"])
            if payload["discount_set"]
            else ""
        )
        r2 = (
            format_pct(payload["rabatt_2"])
            if payload["discount_set"]
            else ""
        )
        match_label = (
            "zugeordnet" if payload["match_status"] == "matched" else "ohne Zuordnung"
        )
        if payload["multi_article"]:
            match_label += " — alle genannten Artikel betroffen"
        data.append(
            [
                payload["supplier_article_number"],
                payload["name"],
                payload["article_numbers_label"],
                payload["rabattcode"],
                format_swiss_number(payload["listenpreis"]),
                r1,
                r2,
                format_swiss_number(payload["ek"]),
                format_swiss_number(payload["ek_chf"]),
                format_swiss_number(payload["vk_chf"]),
                format_pct(payload["marge"]),
                format_swiss_number(payload["current_ek"]),
                format_pct(payload["implied_discount"]),
                match_label,
                payload["row_intent"],
            ]
        )
        if payload["match_status"] == "unmatched":
            unmatched_rows.append(i)
    codes = sorted({p["rabattcode"] for p in payloads if p["rabattcode"]})
    return {
        "runId": run.id,
        "editable": run.status in EDITABLE_STATUSES,
        "editableFields": ["rabatt_1", "rabatt_2", "vk_chf", "row_intent"],
        "fields": fields,
        "columns": columns,
        "data": data,
        "rowIds": [p["id"] for p in payloads],
        "unmatchedRows": unmatched_rows,
        "rabattcodes": codes,
        "editsUrl": f"/bezugsquellen/neu/{run.id}/edits",
        "bulkUrl": f"/bezugsquellen/neu/{run.id}/rabatte",
        "idleMs": 400,
        "discountUnset": summary_counts(rows)["discount_unset"],
    }
