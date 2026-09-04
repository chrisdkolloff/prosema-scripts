"""Read-only supply-source resolve: index, then match against the local mirror."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Supplier,
    SupplierArticleAlias,
    SupplySourceRow,
    SupplySourceRun,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
    WeclappSupplySourcePrice,
)
from app.supply_source_index import pull_supply_source_index

logger = logging.getLogger(__name__)


def fail_run(db: Session, run: SupplySourceRun, message: str) -> None:
    run.status = "failed"
    run.error = message
    db.commit()


def current_price_row(
    prices: list[WeclappSupplySourcePrice],
    *,
    now: datetime | None = None,
) -> WeclappSupplySourcePrice | None:
    now = now or datetime.now(UTC)
    covering: list[WeclappSupplySourcePrice] = []
    open_ended: list[WeclappSupplySourcePrice] = []
    for price in prices:
        start_ok = price.start_date is None or price.start_date <= now
        end_ok = price.end_date is None or price.end_date >= now
        if start_ok and end_ok:
            covering.append(price)
        if price.end_date is None:
            open_ended.append(price)
    chosen = covering or open_ended
    if not chosen:
        return None
    chosen.sort(key=lambda p: p.start_date or datetime.min.replace(tzinfo=UTC), reverse=True)
    return chosen[0]


def _rabattcodes_for_articles(
    db: Session, article_ids: list[str]
) -> str | None:
    if not article_ids:
        return None
    codes: list[str] = []
    seen: set[str] = set()
    rows = db.scalars(
        select(WeclappArticle).where(WeclappArticle.weclapp_article_id.in_(article_ids))
    ).all()
    by_id = {r.weclapp_article_id: r for r in rows}
    for aid in article_ids:
        article = by_id.get(aid)
        code = (article.rabattcode or "").strip() if article else ""
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    if not codes:
        return None
    return codes[0] if len(codes) == 1 else ", ".join(codes)


def _set_articles(row: SupplySourceRow, pairs: list[tuple[str, str]]) -> None:
    numbers: list[str] = []
    ids: list[str] = []
    seen: set[str] = set()
    for number, aid in pairs:
        if aid in seen:
            continue
        seen.add(aid)
        numbers.append(number)
        ids.append(aid)
    row.resolved_article_numbers = numbers
    row.weclapp_article_ids = ids


def _links_for_ss(
    db: Session, ss_id: str
) -> list[WeclappSupplySourceLink]:
    return list(
        db.scalars(
            select(WeclappSupplySourceLink).where(
                WeclappSupplySourceLink.supply_source_weclapp_id == ss_id
            )
        ).all()
    )


def _prices_for_ss(db: Session, ss_id: str) -> list[WeclappSupplySourcePrice]:
    return list(
        db.scalars(
            select(WeclappSupplySourcePrice).where(
                WeclappSupplySourcePrice.supply_source_weclapp_id == ss_id
            )
        ).all()
    )


def _apply_current_ek(row: SupplySourceRow, ss_id: str | None, db: Session) -> None:
    if not ss_id:
        row.current_ek = None
        row.current_ek_currency = None
        return
    price = current_price_row(_prices_for_ss(db, ss_id))
    if price is None:
        row.current_ek = None
        row.current_ek_currency = None
        return
    row.current_ek = price.price
    row.current_ek_currency = price.currency_code


def _text_eq(left: str | None, right: str | None) -> bool:
    a = (left or "").strip()
    b = (right or "").strip()
    return a == b


def _qty_eq(left: object, right: object) -> bool:
    if left in (None, "") and right in (None, ""):
        return True
    if left in (None, "") or right in (None, ""):
        return False
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError, TypeError):
        return str(left) == str(right)


def _intent_for_upload_linked(row: SupplySourceRow) -> str:
    overrides = row.field_overrides or {}
    for key in ("name", "ean", "min_purchase_qty", "procurement_lead_days"):
        if overrides.get(key) == "template":
            return "update"
    return "price_only"


def _apply_upload_divergences(db: Session, row: SupplySourceRow) -> None:
    if not row.weclapp_supply_source_id:
        return
    ss = db.get(WeclappSupplySource, row.weclapp_supply_source_id)
    if ss is None:
        return
    overrides = dict(row.field_overrides or {})

    if not _text_eq(row.template_name, ss.name):
        overrides.setdefault("name", "weclapp")
    if overrides.get("name") == "template":
        row.name = row.template_name
    else:
        row.name = ss.name

    if not _text_eq(row.template_ean, ss.ean):
        overrides.setdefault("ean", "weclapp")
    if overrides.get("ean") == "template":
        row.ean = row.template_ean
    else:
        row.ean = ss.ean

    if not _qty_eq(row.template_min_qty, ss.min_purchase_qty):
        overrides.setdefault("min_purchase_qty", "weclapp")
    if not _qty_eq(row.template_lead_days, ss.procurement_lead_days):
        overrides.setdefault("procurement_lead_days", "weclapp")

    row.field_overrides = overrides
    if row.row_intent in {"update", "price_only"}:
        row.row_intent = _intent_for_upload_linked(row)


def _intent_for_linked_ss(
    row: SupplySourceRow, ss: WeclappSupplySource
) -> str:
    """price_only unless a non-price SS field differs from the template row.

    Pull-sourced rows copy name/ean from the same SS after the index, so they
    classify as price_only. Upload (out of scope) can introduce other diffs.
    """
    if (row.name or None) != (ss.name or None):
        return "update"
    if (row.ean or None) != (ss.ean or None):
        return "update"
    return "price_only"


def _resolve_articles_tier2_3(
    db: Session,
    *,
    supplier_id: int,
    san: str,
    ean: str | None,
) -> tuple[int | None, list[tuple[str, str]]]:
    aliases = list(
        db.scalars(
            select(SupplierArticleAlias).where(
                SupplierArticleAlias.supplier_id == supplier_id,
                SupplierArticleAlias.supplier_article_number == san,
            )
        ).all()
    )
    if aliases:
        return 2, [(a.article_number, a.weclapp_article_id) for a in aliases]
    needle = (ean or "").strip()
    if needle:
        articles = list(
            db.scalars(
                select(WeclappArticle).where(WeclappArticle.ean == needle)
            ).all()
        )
        if articles:
            return 3, [(a.article_number, a.weclapp_article_id) for a in articles]
    return None, []


def _existing_ss_for_articles(
    db: Session,
    *,
    party_id: str,
    article_ids: list[str],
) -> WeclappSupplySourceLink | None:
    if not article_ids:
        return None
    return db.scalars(
        select(WeclappSupplySourceLink).where(
            WeclappSupplySourceLink.weclapp_article_id.in_(article_ids),
            WeclappSupplySourceLink.supplier_party_id == party_id,
        )
    ).first()


def _assign_unit(db: Session, row: SupplySourceRow) -> None:
    """Pre-fill Einheit: article unit if resolved, else SS unit on update-like intents.

    An upload may already have set unit_id from a recognised Einheit name. Keep
    that when there is no article (create without a match uses the file, or
    stays NULL and blocks).
    """
    if row.weclapp_article_ids:
        article = db.get(WeclappArticle, row.weclapp_article_ids[0])
        if article is not None and article.unit_id:
            row.unit_id = article.unit_id
            return
    if row.row_intent in {"update", "price_only", "renumber"} and row.weclapp_supply_source_id:
        ss = db.get(WeclappSupplySource, row.weclapp_supply_source_id)
        if ss is not None:
            row.unit_id = ss.unit_id
            return


def resolve_row(
    db: Session,
    run: SupplySourceRun,
    row: SupplySourceRow,
    *,
    supplier: Supplier,
) -> None:
    try:
        _resolve_row_body(db, run, row, supplier=supplier)
    finally:
        _assign_unit(db, row)


def _resolve_row_body(
    db: Session,
    run: SupplySourceRun,
    row: SupplySourceRow,
    *,
    supplier: Supplier,
) -> None:
    party_id = supplier.weclapp_party_id
    san = row.supplier_article_number
    ss = db.scalars(
        select(WeclappSupplySource).where(
            WeclappSupplySource.supplier_party_id == party_id,
            WeclappSupplySource.supplier_article_number == san,
        )
    ).first()

    if ss is not None:
        row.weclapp_supply_source_id = ss.weclapp_id
        row.weclapp_version = ss.weclapp_version
        _apply_current_ek(row, ss.weclapp_id, db)
        links = _links_for_ss(db, ss.weclapp_id)
        if links:
            row.match_tier = 1
            row.match_status = "matched"
            _set_articles(
                row,
                [(lnk.article_number, lnk.weclapp_article_id) for lnk in links],
            )
            if row.row_intent != "skip":
                row.row_intent = _intent_for_linked_ss(row, ss)
            if not row.rabattcode:
                row.rabattcode = _rabattcodes_for_articles(db, row.weclapp_article_ids)
            return
        if row.row_intent != "skip":
            row.row_intent = "attach"
        tier, pairs = _resolve_articles_tier2_3(
            db, supplier_id=supplier.id, san=san, ean=row.ean or ss.ean
        )
        if pairs:
            row.match_tier = tier
            row.match_status = "matched"
            _set_articles(row, pairs)
            if not row.rabattcode:
                row.rabattcode = _rabattcodes_for_articles(db, row.weclapp_article_ids)
        else:
            row.match_tier = None
            row.match_status = "unmatched"
            _set_articles(row, [])
        return

    row.weclapp_supply_source_id = None
    row.weclapp_version = None
    row.current_ek = None
    row.current_ek_currency = None
    tier, pairs = _resolve_articles_tier2_3(
        db, supplier_id=supplier.id, san=san, ean=row.ean
    )
    if not pairs:
        row.match_tier = None
        row.match_status = "unmatched"
        _set_articles(row, [])
        if row.row_intent != "skip":
            row.row_intent = None
        return

    row.match_tier = tier
    row.match_status = "matched"
    _set_articles(row, pairs)
    if not row.rabattcode:
        row.rabattcode = _rabattcodes_for_articles(db, row.weclapp_article_ids)
    existing = _existing_ss_for_articles(
        db, party_id=party_id, article_ids=row.weclapp_article_ids
    )
    if row.row_intent == "skip":
        return
    if existing is not None:
        row.row_intent = "renumber"
        row.weclapp_supply_source_id = existing.supply_source_weclapp_id
        parent = db.get(WeclappSupplySource, existing.supply_source_weclapp_id)
        if parent is not None:
            row.weclapp_version = parent.weclapp_version
            _apply_current_ek(row, parent.weclapp_id, db)
    else:
        row.row_intent = "create"


def _seed_rows_from_mirror(
    db: Session, run: SupplySourceRun, supplier: Supplier
) -> None:
    sources = list(
        db.scalars(
            select(WeclappSupplySource).where(
                WeclappSupplySource.supplier_party_id == supplier.weclapp_party_id,
                WeclappSupplySource.missing_since.is_(None),
            )
        ).all()
    )
    existing = {
        r.supplier_article_number
        for r in db.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        ).all()
    }
    for ss in sources:
        if not ss.supplier_article_number or ss.supplier_article_number in existing:
            continue
        price = current_price_row(_prices_for_ss(db, ss.weclapp_id))
        row = SupplySourceRow(
            run_id=run.id,
            supplier_article_number=ss.supplier_article_number,
            name=ss.name,
            ean=ss.ean,
            listenpreis=price.price if price else None,
        )
        db.add(row)
        existing.add(ss.supplier_article_number)
    db.flush()


def intent_counts(rows: list[SupplySourceRow]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        key = row.row_intent or "none"
        counts[key] += 1
    return dict(counts)


def tier_counts(rows: list[SupplySourceRow]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        key = str(row.match_tier) if row.match_tier is not None else "none"
        counts[key] += 1
    return dict(counts)


def run_resolve(
    db: Session,
    run: SupplySourceRun,
    *,
    oid: str,
    client: Any | None = None,
    skip_index: bool = False,
) -> dict[str, Any]:
    supplier = db.get(Supplier, run.supplier_id)
    if supplier is None or supplier.deleted_at is not None:
        raise ValueError("Lieferant nicht gefunden")

    index_result: dict[str, Any] = {}
    if not skip_index:
        index_result = pull_supply_source_index(
            db, oid=oid, supplier_id=supplier.id, client=client
        )
        run = db.get(SupplySourceRun, run.id) or run
        raw = index_result.get("datenstand")
        if raw:
            run.datenstand = datetime.fromisoformat(str(raw))
        else:
            run.datenstand = datetime.now(UTC)
    elif run.datenstand is None:
        run.datenstand = datetime.now(UTC)

    if run.source != "upload":
        _seed_rows_from_mirror(db, run, supplier)
    rows = list(
        db.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        ).all()
    )
    for row in rows:
        if row.row_intent == "skip":
            continue
        resolve_row(db, run, row, supplier=supplier)
        if run.source == "upload":
            _apply_upload_divergences(db, row)

    run.status = "preview"
    run.error = None
    db.commit()
    rows = list(
        db.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        ).all()
    )
    result = {
        "run_id": run.id,
        "row_count": len(rows),
        "intent_counts": intent_counts(rows),
        "tier_counts": tier_counts(rows),
        "index": index_result,
    }
    logger.info(
        "supply_source_resolve run_id=%s rows=%s intents=%s tiers=%s",
        run.id,
        len(rows),
        result["intent_counts"],
        result["tier_counts"],
    )
    return result
