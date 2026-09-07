"""Read-only supply-source resolve: index, then match against the local mirror."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ArticleSnapshot,
    ArticleSnapshotRow,
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
from app.weclapp import is_weclapp_auth_failure, job_error_message

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


SAN_FIELDS = (
    "name",
    "ean",
    "listenpreis",
    "listenpreis_raw",
    "rabatt_1",
    "rabatt_2",
    "discount_set",
    "discount_source",
    "unit_id",
    "unit_raw",
    "file_unit_id",
    "unit_overwritten",
    "live_currency_id",
    "resolved_currency_id",
    "currency_overwritten",
    "template_name",
    "template_ean",
    "template_min_qty",
    "template_lead_days",
    "field_overrides",
    "current_ek",
    "current_ek_currency",
    "weclapp_supply_source_id",
    "weclapp_version",
    "created_supply_source_id",
    "vk_override",
)


def _rabattcode_for_article(db: Session, article_id: str | None) -> str | None:
    if not article_id:
        return None
    article = db.get(WeclappArticle, article_id)
    if article is not None:
        code = (article.rabattcode or "").strip()
        if code:
            return code
    snapshot = _latest_completed_snapshot(db)
    if snapshot is None:
        return None
    snap = db.scalars(
        select(ArticleSnapshotRow).where(
            ArticleSnapshotRow.snapshot_id == snapshot.id,
            ArticleSnapshotRow.weclapp_id == article_id,
        )
    ).first()
    if snap is None:
        return None
    from core.article_payload import get_row_value

    code = get_row_value(snap.data or {}, "Rabattcode").strip()
    return code or None


def _clone_san_row(src: SupplySourceRow) -> SupplySourceRow:
    copy = SupplySourceRow(
        run_id=src.run_id,
        supplier_article_number=src.supplier_article_number,
    )
    for field in SAN_FIELDS:
        value = getattr(src, field)
        if field == "field_overrides":
            value = dict(value or {})
        setattr(copy, field, value)
    return copy


def _bind_article(row: SupplySourceRow, number: str | None, article_id: str | None) -> None:
    row.article_number = number
    row.weclapp_article_id = article_id


def _expand_links(
    db: Session,
    row: SupplySourceRow,
    pairs: list[tuple[str, str]],
    *,
    included: bool,
    match_tier: int | None,
    match_status: str,
    intent: str | None,
) -> None:
    if not pairs:
        _bind_article(row, None, None)
        row.match_tier = None
        row.match_status = "unmatched"
        row.included = True
        if row.row_intent != "skip":
            row.row_intent = intent
        return
    first = True
    for number, aid in pairs:
        target = row if first else _clone_san_row(row)
        if not first:
            db.add(target)
        _bind_article(target, number, aid)
        target.match_tier = match_tier
        target.match_status = match_status
        target.included = included if target.row_intent != "skip" else target.included
        if target.row_intent != "skip":
            target.row_intent = intent
        if not target.rabattcode:
            target.rabattcode = _rabattcode_for_article(db, aid)
        first = False
    db.flush()


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
        snapshot_pairs = _articles_from_snapshot_ean(db, needle)
        if snapshot_pairs:
            return 3, snapshot_pairs
    return None, []


def _latest_completed_snapshot(db: Session) -> ArticleSnapshot | None:
    tenant = settings.weclapp_tenant.strip()
    stmt = select(ArticleSnapshot).where(ArticleSnapshot.status == "complete")
    if tenant:
        stmt = stmt.where(ArticleSnapshot.weclapp_tenant == tenant)
    return db.scalars(stmt.order_by(ArticleSnapshot.created_at.desc()).limit(1)).first()


def _articles_from_snapshot_ean(db: Session, ean: str) -> list[tuple[str, str]]:
    snapshot = _latest_completed_snapshot(db)
    if snapshot is None:
        return []
    needle = ean.strip()
    if not needle:
        return []
    ean_col = ArticleSnapshotRow.data["GTIN (EAN-Nummer)"].astext
    rows = list(
        db.scalars(
            select(ArticleSnapshotRow).where(
                ArticleSnapshotRow.snapshot_id == snapshot.id,
                ArticleSnapshotRow.weclapp_id != "",
                or_(ean_col == needle, func.btrim(ean_col) == needle),
            )
        ).all()
    )
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        aid = (row.weclapp_id or "").strip()
        number = (row.article_number or "").strip()
        if not aid or aid in seen:
            continue
        seen.add(aid)
        pairs.append((number, aid))
    return pairs


def _offline_index_warning(db: Session, exc: BaseException) -> str:
    reason = job_error_message(exc) or str(exc)
    snapshot = _latest_completed_snapshot(db)
    if snapshot is not None:
        from app.snapshots import format_snapshot_timestamp

        stand = format_snapshot_timestamp(snapshot.created_at)
        return (
            f"weclapp-Abfrage übersprungen: {reason} "
            f"Abgleich gegen den letzten lokalen Bezugsquellen-Stand. "
            f"Artikel per EAN aus der Artikelübersicht vom {stand}."
        )
    return (
        f"weclapp-Abfrage übersprungen: {reason} "
        f"Abgleich gegen den letzten lokalen Bezugsquellen-Stand."
    )


def _mirror_datenstand(db: Session, supplier: Supplier) -> datetime | None:
    return db.scalar(
        select(func.max(WeclappSupplySource.last_seen_at)).where(
            WeclappSupplySource.supplier_party_id == supplier.weclapp_party_id
        )
    )


def _existing_ss_for_article(
    db: Session,
    *,
    party_id: str,
    article_id: str | None,
) -> WeclappSupplySourceLink | None:
    if not article_id:
        return None
    return db.scalars(
        select(WeclappSupplySourceLink).where(
            WeclappSupplySourceLink.weclapp_article_id == article_id,
            WeclappSupplySourceLink.supplier_party_id == party_id,
        )
    ).first()


def _assign_unit(db: Session, row: SupplySourceRow) -> None:
    """Pre-fill Einheit: article unit if resolved, else SS unit on update-like intents.

    A matched file unit is overwritten when the mirror differs. The file match
    stays on ``file_unit_id`` / ``unit_raw``; ``unit_overwritten`` flags the clash.
    """
    chosen: str | None = None
    if row.weclapp_article_id:
        article = db.get(WeclappArticle, row.weclapp_article_id)
        if article is not None and article.unit_id:
            chosen = article.unit_id
    if chosen is None and row.row_intent in {"update", "price_only", "renumber"}:
        if row.weclapp_supply_source_id:
            ss = db.get(WeclappSupplySource, row.weclapp_supply_source_id)
            if ss is not None:
                chosen = ss.unit_id
    if not chosen:
        return
    file_uid = (row.file_unit_id or "").strip()
    if file_uid and file_uid != str(chosen).strip():
        row.unit_overwritten = True
    row.unit_id = chosen


def _assign_currency_flag(db: Session, run: SupplySourceRun, row: SupplySourceRow) -> None:
    live_id = None
    live_code = (row.current_ek_currency or "").strip().upper()
    if row.weclapp_supply_source_id:
        price = current_price_row(_prices_for_ss(db, row.weclapp_supply_source_id))
        if price is not None:
            live_id = (price.currency_id or "").strip() or None
            if price.currency_code:
                live_code = str(price.currency_code).strip().upper()
    row.live_currency_id = live_id
    resolved_code = (run.einkaufswaehrung or "").strip().upper()
    if live_code and resolved_code and live_code != resolved_code:
        row.currency_overwritten = True


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
        siblings = list(
            db.scalars(
                select(SupplySourceRow).where(
                    SupplySourceRow.run_id == run.id,
                    SupplySourceRow.supplier_article_number == row.supplier_article_number,
                )
            ).all()
        )
        lead = siblings[0] if siblings else row
        _assign_unit(db, lead)
        _assign_currency_flag(db, run, lead)
        for sibling in siblings:
            sibling.unit_id = lead.unit_id
            sibling.unit_raw = lead.unit_raw
            sibling.file_unit_id = lead.file_unit_id
            sibling.unit_overwritten = lead.unit_overwritten
            sibling.live_currency_id = lead.live_currency_id
            sibling.resolved_currency_id = lead.resolved_currency_id
            sibling.currency_overwritten = lead.currency_overwritten


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
            pairs = [(lnk.article_number, lnk.weclapp_article_id) for lnk in links]
            intent = None if row.row_intent == "skip" else _intent_for_linked_ss(row, ss)
            _expand_links(
                db,
                row,
                pairs,
                included=True,
                match_tier=1,
                match_status="matched",
                intent=intent,
            )
            return
        if row.row_intent != "skip":
            row.row_intent = "attach"
        tier, pairs = _resolve_articles_tier2_3(
            db, supplier_id=supplier.id, san=san, ean=row.ean or ss.ean
        )
        if pairs:
            _expand_links(
                db,
                row,
                pairs,
                included=tier == 2,
                match_tier=tier,
                match_status="matched",
                intent="attach",
            )
        else:
            _expand_links(
                db,
                row,
                [],
                included=True,
                match_tier=None,
                match_status="unmatched",
                intent="attach",
            )
        return

    row.weclapp_supply_source_id = None
    row.weclapp_version = None
    row.current_ek = None
    row.current_ek_currency = None
    tier, pairs = _resolve_articles_tier2_3(
        db, supplier_id=supplier.id, san=san, ean=row.ean
    )
    if not pairs:
        _expand_links(
            db,
            row,
            [],
            included=True,
            match_tier=None,
            match_status="unmatched",
            intent=None,
        )
        return

    _expand_links(
        db,
        row,
        pairs,
        included=tier == 2,
        match_tier=tier,
        match_status="matched",
        intent="create",
    )
    party_id = supplier.weclapp_party_id
    siblings = list(
        db.scalars(
            select(SupplySourceRow).where(
                SupplySourceRow.run_id == run.id,
                SupplySourceRow.supplier_article_number == san,
            )
        ).all()
    )
    for sibling in siblings:
        existing = _existing_ss_for_article(
            db, party_id=party_id, article_id=sibling.weclapp_article_id
        )
        if sibling.row_intent == "skip":
            continue
        if existing is not None:
            sibling.row_intent = "renumber"
            sibling.weclapp_supply_source_id = existing.supply_source_weclapp_id
            parent = db.get(WeclappSupplySource, existing.supply_source_weclapp_id)
            if parent is not None:
                sibling.weclapp_version = parent.weclapp_version
                _apply_current_ek(sibling, parent.weclapp_id, db)
        else:
            sibling.row_intent = "create"


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
    offline_warning: str | None = None
    if not skip_index:
        try:
            index_result = pull_supply_source_index(
                db, oid=oid, supplier_id=supplier.id, client=client
            )
        except Exception as exc:
            if not is_weclapp_auth_failure(exc):
                raise
            offline_warning = _offline_index_warning(db, exc)
            index_result = {"skipped": True, "reason": str(exc)}
            logger.warning(
                "supply_source_resolve run_id=%s skipped live index: %s",
                run.id,
                exc,
            )
            run = db.get(SupplySourceRun, run.id) or run
            if run.datenstand is None:
                run.datenstand = _mirror_datenstand(db, supplier)
        else:
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
        expanded = list(
            db.scalars(
                select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
            ).all()
        )
        for row in expanded:
            _apply_upload_divergences(db, row)

    run.status = "preview"
    run.error = offline_warning
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
