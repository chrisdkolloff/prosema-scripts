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
    SupplierArticleAliasesAudit,
    SupplySourceRow,
    SupplySourceRun,
    SupplySourceUpload,
    WeclappArticle,
    WeclappSupplySource,
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


def parse_aufschlag_percent(raw: object) -> Decimal:
    """UI is percent points (50 → 0.50 stored). Stored value stays a markup fraction."""
    if raw is None:
        raise SupplySourceRunError("Aufschlag fehlt.")
    text = str(raw).strip().replace("%", "").replace(" ", "").replace("'", "")
    if text == "":
        raise SupplySourceRunError("Aufschlag fehlt.")
    if "," in text and "." in text:
        if text.rindex(",") > text.rindex("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        points = Decimal(text)
    except InvalidOperation as extra:
        raise SupplySourceRunError("Aufschlag ist keine Zahl.") from extra
    if points < 0:
        raise SupplySourceRunError("Aufschlag darf nicht negativ sein.")
    return points / Decimal(100)


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


def create_upload_run(
    db: Session,
    *,
    supplier_id: int,
    filename: str,
    content: bytes,
    user: Mapping[str, Any],
) -> SupplySourceRun:
    from app.supply_source_templates import get_or_create_active_template
    from app.supply_source_upload import SupplySourceParseError, parse_upload_bytes

    supplier = db.get(Supplier, supplier_id)
    if supplier is None or supplier.deleted_at is not None:
        raise SupplySourceRunError("Lieferant nicht gefunden.")
    if running_for_supplier(db, supplier.id) is not None:
        raise SupplySourceRunError("Für diesen Lieferanten läuft bereits ein Abgleich.")
    template = get_or_create_active_template(db, supplier.id, user=user)
    columns = template.columns if isinstance(template.columns, list) else []
    try:
        parsed = parse_upload_bytes(
            db, content, filename=filename, columns=columns
        )
    except SupplySourceParseError as exc:
        raise SupplySourceRunError("\n".join(exc.messages)) from exc

    upload = SupplySourceUpload(
        supplier_id=supplier.id,
        template_id=template.id,
        filename=filename or "upload.xlsx",
        content=content,
        row_count=len(parsed.rows),
        parse_summary={
            "accepted": len(parsed.rows),
            "rejected": parsed.row_errors,
            "unmatched_units": parsed.unmatched_units,
        },
        uploaded_by=str(user["oid"]),
        uploaded_by_name=str(user.get("name") or user["oid"]),
    )
    db.add(upload)
    db.flush()

    kurs = supplier.default_kurs
    if supplier.einkaufswaehrung == "CHF":
        kurs = Decimal("1.0")
    run = SupplySourceRun(
        supplier_id=supplier.id,
        status="running",
        source="upload",
        template_id=template.id,
        upload_id=upload.id,
        einkaufswaehrung=supplier.einkaufswaehrung,
        kurs=kurs,
        verkaufswaehrung=supplier.default_verkaufswaehrung,
        aufschlag=supplier.default_aufschlag,
        created_by=str(user["oid"]),
        created_by_name=str(user.get("name") or user["oid"]),
    )
    db.add(run)
    db.flush()
    for item in parsed.rows:
        db.add(
            SupplySourceRow(
                run_id=run.id,
                supplier_article_number=item.supplier_article_number,
                name=item.name,
                ean=item.ean,
                listenpreis=item.listenpreis,
                rabattcode=item.rabattcode,
                unit_id=item.unit_id,
                template_name=item.name,
                template_ean=item.ean,
                template_min_qty=item.min_purchase_qty,
                template_lead_days=item.procurement_lead_days,
                field_overrides={},
            )
        )
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
        "create_no_unit": sum(
            1
            for r in rows
            if r.row_intent == "create" and not str(r.unit_id or "").strip()
        ),
        "attach_no_unit": sum(
            1
            for r in rows
            if r.row_intent == "attach" and not str(r.unit_id or "").strip()
        ),
        "skip": sum(1 for r in rows if r.row_intent == "skip"),
        "total": len(rows),
        "attach": sum(1 for r in rows if r.row_intent == "attach"),
    }


def approval_blockers(rows: list[SupplySourceRow]) -> dict[str, int]:
    unmatched = 0
    unset = 0
    create_no_unit = 0
    attach_no_unit = 0
    for row in rows:
        if row.row_intent == "skip":
            continue
        if row.match_status == "unmatched":
            unmatched += 1
        if not row.discount_set:
            unset += 1
        if row.row_intent == "create" and not str(row.unit_id or "").strip():
            create_no_unit += 1
        # Guard: attach without unit should not occur (those rows are unmatched
        # today). Same block as create so a future matcher cannot approve a
        # write weclapp would reject.
        if row.row_intent == "attach" and not str(row.unit_id or "").strip():
            attach_no_unit += 1
    return {
        "unmatched": unmatched,
        "discount_unset": unset,
        "create_no_unit": create_no_unit,
        "attach_no_unit": attach_no_unit,
    }


def can_approve(rows: list[SupplySourceRow]) -> bool:
    blocks = approval_blockers(rows)
    return (
        blocks["unmatched"] == 0
        and blocks["discount_unset"] == 0
        and blocks["create_no_unit"] == 0
        and blocks["attach_no_unit"] == 0
    )


def load_rows(db: Session, run_id: int) -> list[SupplySourceRow]:
    return list(
        db.scalars(
            select(SupplySourceRow)
            .where(SupplySourceRow.run_id == run_id)
            .order_by(SupplySourceRow.supplier_article_number)
        ).all()
    )


def assert_editable(run: SupplySourceRun) -> None:
    if run.status not in EDITABLE_STATUSES or run.approved_at is not None:
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


OVERRIDE_FIELDS = ("name", "ean", "min_purchase_qty", "procurement_lead_days")


def _apply_override_choice(row: SupplySourceRow, key: str, choice: str) -> None:
    ss = None
    session = Session.object_session(row)
    if session is not None and row.weclapp_supply_source_id:
        ss = session.get(WeclappSupplySource, row.weclapp_supply_source_id)
    if key == "name":
        row.name = row.template_name if choice == "template" else (ss.name if ss else row.name)
    elif key == "ean":
        row.ean = row.template_ean if choice == "template" else (ss.ean if ss else row.ean)


def apply_template_overrides(
    db: Session,
    run: SupplySourceRun,
    *,
    row_ids: list[int],
) -> int:
    """Set every divergent field on the given rows to the template value."""
    assert_editable(run)
    if not row_ids:
        raise SupplySourceRunError("Keine Zeilen ausgewählt.")
    rows = list(
        db.scalars(
            select(SupplySourceRow).where(
                SupplySourceRow.run_id == run.id,
                SupplySourceRow.id.in_(row_ids),
            )
        ).all()
    )
    from app.supply_source_resolve import _intent_for_upload_linked

    count = 0
    for row in rows:
        overrides = dict(row.field_overrides or {})
        if not overrides:
            continue
        for key in OVERRIDE_FIELDS:
            if key in overrides:
                overrides[key] = "template"
                _apply_override_choice(row, key, "template")
        row.field_overrides = overrides
        if row.row_intent in {"update", "price_only"}:
            row.row_intent = _intent_for_upload_linked(row)
        count += 1
    db.commit()
    return count


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
        elif field == "unit_id":
            if row.row_intent not in {"create", "attach"}:
                raise SupplySourceRunError(
                    "Einheit einer bestehenden Bezugsquelle lässt sich nicht ändern."
                )
            uid = str(value or "").strip()
            row.unit_id = uid or None
        elif field in {
            "override_name",
            "override_ean",
            "override_min_qty",
            "override_lead_days",
        }:
            key = {
                "override_name": "name",
                "override_ean": "ean",
                "override_min_qty": "min_purchase_qty",
                "override_lead_days": "procurement_lead_days",
            }[field]
            choice = str(value or "weclapp").strip()
            if choice not in {"weclapp", "template"}:
                raise SupplySourceRunError("Ungültige Feldwahl.")
            overrides = dict(row.field_overrides or {})
            if key not in overrides:
                continue
            overrides[key] = choice
            row.field_overrides = overrides
            _apply_override_choice(row, key, choice)
            if row.row_intent in {"update", "price_only"}:
                from app.supply_source_resolve import _intent_for_upload_linked

                row.row_intent = _intent_for_upload_linked(row)
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
        db.flush()
        db.add(
            SupplierArticleAliasesAudit(
                entity="alias",
                entity_id=existing.id,
                action="created",
                before=None,
                after={
                    "supplier_article_number": existing.supplier_article_number,
                    "article_number": existing.article_number,
                    "weclapp_article_id": existing.weclapp_article_id,
                    "source": existing.source,
                },
                actor_oid=oid,
                actor_name=name or oid,
            )
        )
    else:
        before = {
            "article_number": existing.article_number,
            "weclapp_article_id": existing.weclapp_article_id,
            "source": existing.source,
        }
        existing.source = "manual"
        existing.confirmed_by = oid
        existing.confirmed_at = datetime.now(UTC)
        db.add(
            SupplierArticleAliasesAudit(
                entity="alias",
                entity_id=existing.id,
                action="updated",
                before=before,
                after={
                    "article_number": existing.article_number,
                    "weclapp_article_id": existing.weclapp_article_id,
                    "source": existing.source,
                },
                actor_oid=oid,
                actor_name=name or oid,
            )
        )
    supplier = db.get(Supplier, run.supplier_id)
    if supplier is None:
        raise SupplySourceRunError("Lieferant nicht gefunden.")
    resolve_row(db, run, row, supplier=supplier)
    db.commit()
    return existing


def approve_run(db: Session, run: SupplySourceRun, user: Mapping[str, Any]) -> None:
    if run.status not in {"preview", "approved"}:
        raise SupplySourceRunError("Dieser Lauf kann jetzt nicht geschrieben werden.")
    rows = load_rows(db, run.id)
    if not can_approve(rows):
        raise SupplySourceRunError(
            "Freigabe nicht möglich: offene Zuordnungen, fehlende Rabattsätze oder fehlende Einheit."
        )
    from app.supply_source_apply import enqueue_apply_chunk

    enqueue_apply_chunk(db, run, user)


def row_payload(
    row: SupplySourceRow,
    run: SupplySourceRun,
    *,
    supply_source: WeclappSupplySource | None = None,
) -> dict[str, Any]:
    prices = derived_prices(row, run)
    numbers = list(row.resolved_article_numbers or [])
    overrides = dict(row.field_overrides or {})
    weclapp_name = supply_source.name if supply_source is not None else row.name
    weclapp_ean = supply_source.ean if supply_source is not None else row.ean
    weclapp_min = (
        supply_source.min_purchase_qty if supply_source is not None else None
    )
    weclapp_lead = (
        supply_source.procurement_lead_days if supply_source is not None else None
    )
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
        "unit_id": row.unit_id or "",
        "template_name": row.template_name or "",
        "template_ean": row.template_ean or "",
        "template_min_qty": row.template_min_qty,
        "template_lead_days": row.template_lead_days,
        "weclapp_name": weclapp_name or "",
        "weclapp_ean": weclapp_ean or "",
        "weclapp_min_qty": weclapp_min,
        "weclapp_lead_days": weclapp_lead,
        "override_name": overrides.get("name") or "",
        "override_ean": overrides.get("ean") or "",
        "override_min_qty": overrides.get("min_purchase_qty") or "",
        "override_lead_days": overrides.get("procurement_lead_days") or "",
        "has_divergence": bool(overrides),
    }


def _override_cell(choice: str) -> str:
    return choice if choice in {"weclapp", "template"} else ""


def build_grid_config(run: SupplySourceRun, rows: list[SupplySourceRow]) -> dict[str, Any]:
    from app.weclapp_units import UNIT_LOCKED_HINT, units_for_dropdown

    session = Session.object_session(run)
    units = units_for_dropdown(session) if session is not None else []
    unit_source = [[u["id"], u["name"]] for u in units]
    ss_ids = [r.weclapp_supply_source_id for r in rows if r.weclapp_supply_source_id]
    ss_map: dict[str, WeclappSupplySource] = {}
    if session is not None and ss_ids:
        ss_map = {
            s.weclapp_id: s
            for s in session.scalars(
                select(WeclappSupplySource).where(
                    WeclappSupplySource.weclapp_id.in_(ss_ids)
                )
            )
        }
    payloads = [
        row_payload(
            row,
            run,
            supply_source=ss_map.get(row.weclapp_supply_source_id or ""),
        )
        for row in rows
    ]
    show_div = any(p["has_divergence"] for p in payloads)
    fields = [
        "supplier_article_number",
        "name",
        "article_numbers_label",
        "unit_id",
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
        {
            "title": "Einheit",
            "width": 110,
            "type": "dropdown",
            "source": unit_source,
            "autocomplete": True,
        },
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
    override_source = [
        ["weclapp", "weclapp belassen"],
        ["template", "Vorlagenwert"],
    ]
    if show_div:
        fields.extend(
            ["override_name", "override_ean", "override_min_qty", "override_lead_days"]
        )
        columns.extend(
            [
                {
                    "title": "Bezeichnung von",
                    "width": 140,
                    "type": "dropdown",
                    "source": override_source,
                },
                {
                    "title": "EAN von",
                    "width": 140,
                    "type": "dropdown",
                    "source": override_source,
                },
                {
                    "title": "Mindestmenge von",
                    "width": 150,
                    "type": "dropdown",
                    "source": override_source,
                },
                {
                    "title": "Lieferzeit von",
                    "width": 140,
                    "type": "dropdown",
                    "source": override_source,
                },
            ]
        )
    data = []
    unmatched_rows: list[int] = []
    unit_locked_rows: list[int] = []
    divergence_titles: list[str] = []
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
        row_data = [
                payload["supplier_article_number"],
                payload["name"],
                payload["article_numbers_label"],
                payload["unit_id"],
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
        if show_div:
            row_data.extend(
                [
                    _override_cell(payload["override_name"]),
                    _override_cell(payload["override_ean"]),
                    _override_cell(payload["override_min_qty"]),
                    _override_cell(payload["override_lead_days"]),
                ]
            )
        data.append(row_data)
        if payload["match_status"] == "unmatched":
            unmatched_rows.append(i)
        if payload["row_intent"] not in {"create", "attach"}:
            unit_locked_rows.append(i)
        titles: list[str] = []
        if payload["override_name"]:
            titles.append(
                f"Bezeichnung weclapp: {payload['weclapp_name'] or '—'} · "
                f"Vorlage: {payload['template_name'] or '—'}"
            )
        if payload["override_ean"]:
            titles.append(
                f"EAN weclapp: {payload['weclapp_ean'] or '—'} · "
                f"Vorlage: {payload['template_ean'] or '—'}"
            )
        if payload["override_min_qty"]:
            titles.append(
                "Mindestmenge weclapp: "
                f"{payload['weclapp_min_qty'] if payload['weclapp_min_qty'] is not None else '—'} · "
                f"Vorlage: {payload['template_min_qty'] if payload['template_min_qty'] is not None else '—'}"
            )
        if payload["override_lead_days"]:
            titles.append(
                "Lieferzeit weclapp: "
                f"{payload['weclapp_lead_days'] if payload['weclapp_lead_days'] is not None else '—'} · "
                f"Vorlage: {payload['template_lead_days'] if payload['template_lead_days'] is not None else '—'}"
            )
        divergence_titles.append(" | ".join(titles))
    codes = sorted({p["rabattcode"] for p in payloads if p["rabattcode"]})
    counts = summary_counts(rows)
    return {
        "runId": run.id,
        "editable": run.status in EDITABLE_STATUSES and run.approved_at is None,
        "editableFields": [
            "rabatt_1",
            "rabatt_2",
            "vk_chf",
            "row_intent",
            "unit_id",
            "override_name",
            "override_ean",
            "override_min_qty",
            "override_lead_days",
        ],
        "fields": fields,
        "columns": columns,
        "data": data,
        "rowIds": [p["id"] for p in payloads],
        "unmatchedRows": unmatched_rows,
        "unitLockedRows": unit_locked_rows,
        "unitLockedHint": UNIT_LOCKED_HINT,
        "units": units,
        "divergenceTitles": divergence_titles,
        "rabattcodes": codes,
        "editsUrl": f"/bezugsquellen/neu/{run.id}/edits",
        "bulkUrl": f"/bezugsquellen/neu/{run.id}/rabatte",
        "templateBulkUrl": f"/bezugsquellen/neu/{run.id}/vorlagenwert",
        "idleMs": 400,
        "discountUnset": counts["discount_unset"],
        "createNoUnit": counts["create_no_unit"] + counts["attach_no_unit"],
        "showDivergence": show_div,
    }
