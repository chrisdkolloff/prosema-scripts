"""Chunked weclapp writes for supply_source_row. Mirror is never the payload source."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.models import Supplier, SupplySourceRow, SupplySourceRun
from app.supply_source_payload import (
    SupplySourcePayloadError,
    build_article_attach_put,
    build_supply_source_post,
    build_supply_source_put,
    live_price_ids,
    sanitize_price_row,
)
from app.supply_source_runs import can_approve, derived_prices, load_rows
from app.weclapp import WeclappLicenceMissing, WeclappTokenInvalid, map_weclapp_error
from scripts.weclapp.client import WeclappError

# Live Dural history uses a 1 ms seam (end …799000, next start …800000).
# A day-truncated write also 400'd "The new prices overlap." Which boundary
# weclapp actually stores is still open. Do not "fix" overlaps by retrying
# with a different offset.
BOUNDARY_OFFSET_MS = 1

MSG_OVERLAP = (
    "Preis-Eintritt überschneidet sich mit einem bestehenden Preiszeitraum. "
    "Bitte ein anderes Datum wählen. Den Abstand nicht stillschweigend ändern."
)
MSG_AUTH = (
    "Schreiben abgebrochen: weclapp-Zugang ungültig oder ohne Lizenz. "
    "Spätere Zeilen wurden nicht angefasst. Token unter Einstellungen prüfen."
)
MSG_NO_EINTRITT = "Preis-Eintritt fehlt. Bitte setzen, bevor Preise geschrieben werden."
MSG_NO_UNIT = "Mengeneinheit fehlt. Anlegen nicht möglich."
MSG_NO_CURRENCY = "Währung in weclapp nicht gefunden. Schreiben abgebrochen für diese Zeile."
MSG_UNKNOWN = (
    "Schreiben unklar: Verbindung unterbrochen. Bitte diese Zeile prüfen, "
    "nicht blind erneut anwenden."
)
MSG_CONFLICT = (
    "Die Bezugsquelle wurde seit dem Abgleich in weclapp geändert. "
    "Nicht erneut schreiben — zuerst neu abgleichen."
)

ENTITY_TYPE = "weclapp_supply_source"


class SupplySourceAuthAbort(Exception):
    def __init__(self, message: str = MSG_AUTH):
        super().__init__(message)
        self.message = message


def epoch_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def _dt_from_ms(raw: object) -> datetime | None:
    if raw in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except (TypeError, ValueError):
        return None


def _current_live_price(live: Mapping[str, Any]) -> dict[str, Any] | None:
    prices = [p for p in (live.get("articlePrices") or []) if isinstance(p, dict)]
    now = datetime.now(UTC)
    covering: list[dict[str, Any]] = []
    open_ended: list[dict[str, Any]] = []
    for raw in prices:
        start = _dt_from_ms(raw.get("startDate"))
        end = _dt_from_ms(raw.get("endDate"))
        start_ok = start is None or start <= now
        end_ok = end is None or end >= now
        if start_ok and end_ok:
            covering.append(raw)
        if end is None:
            open_ended.append(raw)
    chosen = covering or open_ended
    if not chosen:
        return None

    def start_key(row: dict[str, Any]) -> datetime:
        return _dt_from_ms(row.get("startDate")) or datetime.min.replace(tzinfo=UTC)

    chosen.sort(key=start_key, reverse=True)
    return chosen[0]


def _currency_id(client: Any, code: str, live_current: dict[str, Any] | None) -> str | None:
    if live_current:
        existing = str(live_current.get("currencyId") or "").strip()
        if existing:
            return existing
    payload = client.get("/currency", params={"pageSize": 1000})
    rows = payload.get("result") if isinstance(payload, dict) else payload
    needle = (code or "").strip().upper()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("isoCode") or "").strip().upper()
        if name == needle:
            return str(row.get("id") or "").strip() or None
    return None


def rebuild_article_prices(
    live: Mapping[str, Any],
    *,
    ek: Decimal,
    currency_id: str,
    preis_eintritt: datetime,
) -> list[dict[str, Any]]:
    allowed = live_price_ids(live)
    current = _current_live_price(live)
    start_ms = epoch_ms(preis_eintritt)
    end_ms = start_ms - BOUNDARY_OFFSET_MS
    rebuilt: list[dict[str, Any]] = []
    for raw in live.get("articlePrices") or []:
        if not isinstance(raw, dict):
            continue
        row = sanitize_price_row(raw, allowed_ids=allowed)
        if current is not None and raw is current:
            row["endDate"] = end_ms
        rebuilt.append(row)
    rebuilt.append(
        {
            "price": str(ek),
            "currencyId": currency_id,
            "startDate": start_ms,
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
        }
    )
    return rebuilt


def _prices_equivalent(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    def norm(rows: list[dict[str, Any]]) -> list[tuple]:
        out = []
        for row in rows:
            out.append(
                (
                    str(row.get("id") or ""),
                    str(row.get("price") or ""),
                    str(row.get("currencyId") or ""),
                    str(row.get("startDate") or ""),
                    str(row.get("endDate") or ""),
                )
            )
        return sorted(out)

    return norm(left) == norm(right)


def _overlap_error(detail: Any) -> bool:
    if detail is None:
        return False
    if isinstance(detail, dict):
        chunks = [str(detail.get("detail") or ""), str(detail.get("error") or "")]
        for item in detail.get("messages") or []:
            if isinstance(item, dict):
                chunks.append(str(item.get("message") or ""))
            else:
                chunks.append(str(item))
        text = " ".join(chunks)
    else:
        text = str(detail)
    return "overlap" in text.casefold()


def pending_rows(db: Session, run: SupplySourceRun) -> list[SupplySourceRow]:
    rows = load_rows(db, run.id)
    return [
        row
        for row in rows
        if row.applied_at is None and row.apply_outcome is None
    ]


def next_chunk(db: Session, run: SupplySourceRun) -> list[SupplySourceRow]:
    pending = pending_rows(db, run)
    return pending[: max(int(run.chunk_size or 50), 1)]


def apply_summary(rows: list[SupplySourceRow]) -> dict[str, int]:
    intents = [r.row_intent for r in rows if r.row_intent != "skip"]
    return {
        "total": len(intents),
        "price_only": sum(1 for i in intents if i == "price_only"),
        "update": sum(1 for i in intents if i == "update"),
        "create": sum(1 for i in intents if i == "create"),
        "attach": sum(1 for i in intents if i == "attach"),
        "renumber": sum(1 for i in intents if i == "renumber"),
        "skip": sum(1 for r in rows if r.row_intent == "skip"),
    }


class _ApplyCtx:
    def __init__(
        self,
        db: Session,
        run: SupplySourceRun,
        row: SupplySourceRow,
        client: Any,
        actor: Mapping[str, Any],
        chunk_index: int,
    ):
        self.db = db
        self.run = run
        self.row = row
        self.client = client
        self.actor = actor
        self.chunk_index = chunk_index
        self.http_writes = 0
        self.after_create_hook = None
        self.intended_after: Any = None


def _finish(
    ctx: _ApplyCtx,
    outcome: str,
    *,
    detail: dict[str, Any] | None = None,
    message: str | None = None,
) -> str:
    row = ctx.row
    payload = dict(detail or {})
    if message:
        payload["message"] = message
    payload["intent"] = row.row_intent
    payload["articles"] = list(row.resolved_article_numbers or [])
    row.apply_outcome = outcome
    row.apply_detail = payload
    row.applied_at = datetime.now(UTC)
    row.chunk_id = ctx.chunk_index
    record_audit_log(
        ctx.db,
        actor=ctx.actor,
        entity_type=ENTITY_TYPE,
        entity_id=str(row.id),
        action=outcome.lower(),
        detail=payload,
    )
    ctx.db.commit()
    return outcome


def _handle_error(ctx: _ApplyCtx, exc: WeclappError, *, before: Any = None) -> str:
    mapped = map_weclapp_error(exc)
    if isinstance(mapped, (WeclappTokenInvalid, WeclappLicenceMissing)):
        _finish(ctx, "AUTH", detail={"error": exc.detail}, message=MSG_AUTH)
        raise SupplySourceAuthAbort() from exc
    status = exc.status_code
    if status == 404:
        return _finish(ctx, "GONE", detail={"error": exc.detail})
    if status == 409:
        return _finish(
            ctx, "CONFLICT", detail={"error": exc.detail}, message=MSG_CONFLICT
        )
    if status == 400:
        message = MSG_OVERLAP if _overlap_error(exc.detail) else (
            "weclapp hat die Änderung abgelehnt. Christopher prüft die technische Meldung."
        )
        return _finish(
            ctx,
            "REJECTED",
            detail={"error": exc.detail, "before": before},
            message=message,
        )
    if status is None or status == 429 or (isinstance(status, int) and status >= 500):
        return _reconcile_unknown(ctx, exc, before=before)
    return _finish(ctx, "REJECTED", detail={"error": exc.detail}, message=str(exc))


def _reconcile_unknown(ctx: _ApplyCtx, exc: WeclappError, *, before: Any) -> str:
    ss_id = ctx.row.weclapp_supply_source_id or ctx.row.created_supply_source_id
    intended = ctx.intended_after
    if intended is None and ctx.row.apply_detail:
        intended = ctx.row.apply_detail.get("after")
    try:
        live = ctx.client.get(f"/articleSupplySource/id/{ss_id}") if ss_id else None
    except WeclappError:
        live = None
    after_prices = None
    if isinstance(live, dict):
        after_prices = live.get("articlePrices")
    if isinstance(intended, list) and after_prices is not None and _prices_equivalent(
        [p for p in intended if isinstance(p, dict)],
        [p for p in after_prices if isinstance(p, dict)],
    ):
        return _finish(
            ctx,
            "PRICE_UPDATED",
            detail={"reconciled": True, "after": after_prices},
        )
    if before is not None and after_prices is not None and _prices_equivalent(
        [p for p in before if isinstance(p, dict)],
        [p for p in after_prices if isinstance(p, dict)],
    ):
        return _finish(
            ctx,
            "REJECTED",
            detail={"reconciled": True, "error": getattr(exc, "detail", None)},
            message=MSG_UNKNOWN,
        )
    return _finish(
        ctx,
        "UNKNOWN",
        detail={"error": getattr(exc, "detail", None), "before": before, "after": after_prices},
        message=MSG_UNKNOWN,
    )


def _get_live_ss(ctx: _ApplyCtx, ss_id: str) -> dict[str, Any] | str:
    try:
        live = ctx.client.get(f"/articleSupplySource/id/{ss_id}")
    except WeclappError as exc:
        return _handle_error(ctx, exc)
    if not isinstance(live, dict):
        return _finish(ctx, "UNKNOWN", message=MSG_UNKNOWN)
    return live


def _put_ss(ctx: _ApplyCtx, body: dict[str, Any], params: dict[str, str], *, before: Any) -> Any:
    ctx.http_writes += 1
    ctx.intended_after = body.get("articlePrices", body)
    return ctx.client.put(
        f"/articleSupplySource/id/{body['id']}",
        params=params,
        json=body,
    )


def _apply_skip(ctx: _ApplyCtx) -> str:
    row = ctx.row
    row.apply_outcome = None
    row.apply_detail = {"skipped": True}
    row.applied_at = datetime.now(UTC)
    row.chunk_id = ctx.chunk_index
    record_audit_log(
        ctx.db,
        actor=ctx.actor,
        entity_type=ENTITY_TYPE,
        entity_id=str(row.id),
        action="skip",
        detail={"skipped": True},
    )
    ctx.db.commit()
    return "SKIPPED"


def _ek(ctx: _ApplyCtx) -> Decimal | None:
    prices = derived_prices(ctx.row, ctx.run)
    return prices["ek"]


def _price_fields_changed(live: Mapping[str, Any], rebuilt: list[dict[str, Any]]) -> bool:
    allowed = live_price_ids(live)
    current = [
        sanitize_price_row(p, allowed_ids=allowed)
        for p in (live.get("articlePrices") or [])
        if isinstance(p, dict)
    ]
    return not _prices_equivalent(current, rebuilt)


def _non_price_updates(row: SupplySourceRow, live: Mapping[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if row.name and str(live.get("name") or "") != row.name:
        updates["name"] = row.name
    if row.ean and str(live.get("ean") or "") != row.ean:
        updates["ean"] = row.ean
    return updates


def _apply_price_or_update(ctx: _ApplyCtx, *, intent: str) -> str:
    row = ctx.row
    ss_id = row.weclapp_supply_source_id
    if not ss_id:
        return _finish(ctx, "GONE", message="Keine Bezugsquelle zum Schreiben.")
    live = _get_live_ss(ctx, ss_id)
    if isinstance(live, str):
        return live
    live_version = str(live.get("version") or "")
    if str(row.weclapp_version or "") != live_version:
        return _finish(ctx, "CONFLICT", detail={"live_version": live_version}, message=MSG_CONFLICT)
    if ctx.run.preis_eintritt is None:
        return _finish(ctx, "REJECTED", message=MSG_NO_EINTRITT)
    ek = _ek(ctx)
    if ek is None:
        return _finish(ctx, "REJECTED", message="Einkaufspreis fehlt.")
    current = _current_live_price(live)
    currency_id = _currency_id(ctx.client, ctx.run.einkaufswaehrung, current)
    if not currency_id:
        return _finish(ctx, "REJECTED", message=MSG_NO_CURRENCY)
    rebuilt = rebuild_article_prices(
        live, ek=ek, currency_id=currency_id, preis_eintritt=ctx.run.preis_eintritt
    )
    extra = _non_price_updates(row, live) if intent == "update" else {}
    current_price_val = None
    if current and current.get("price") not in (None, ""):
        try:
            current_price_val = Decimal(str(current.get("price")))
        except (InvalidOperation, ValueError, TypeError):
            current_price_val = None
    same_price = (
        current_price_val is not None
        and current_price_val == ek
        and (
            not current
            or str(current.get("currencyId") or "") == str(currency_id)
        )
    )
    if same_price and not extra:
        return _finish(
            ctx,
            "UNCHANGED",
            detail={"before": live.get("articlePrices"), "version": live_version},
        )
    try:
        body, params = build_supply_source_put(
            supply_source_id=ss_id,
            version=live_version,
            article_prices=rebuilt,
            live_get=live,
            name=extra.get("name"),
            ean=extra.get("ean"),
        )
    except SupplySourcePayloadError as exc:
        return _finish(ctx, "REJECTED", message=str(exc))
    try:
        returned = _put_ss(ctx, body, params, before=live.get("articlePrices"))
    except WeclappError as exc:
        return _handle_error(ctx, exc, before=live.get("articlePrices"))
    outcome = "UPDATED" if extra else "PRICE_UPDATED"
    after_prices = returned.get("articlePrices") if isinstance(returned, dict) else None
    if row.weclapp_version is not None and isinstance(returned, dict):
        row.weclapp_version = str(returned.get("version") or row.weclapp_version)
    return _finish(
        ctx,
        outcome,
        detail={
            "before": live.get("articlePrices"),
            "after": after_prices,
            "fields": extra,
        },
    )


def _apply_renumber(ctx: _ApplyCtx) -> str:
    row = ctx.row
    ss_id = row.weclapp_supply_source_id
    if not ss_id:
        return _finish(ctx, "GONE")
    live = _get_live_ss(ctx, ss_id)
    if isinstance(live, str):
        return live
    live_version = str(live.get("version") or "")
    if str(row.weclapp_version or "") != live_version:
        return _finish(ctx, "CONFLICT", message=MSG_CONFLICT)
    old = str(live.get("articleNumber") or "")
    new = row.supplier_article_number
    if old == new:
        return _finish(ctx, "UNCHANGED", detail={"articleNumber": old})
    body, params = build_supply_source_put(
        supply_source_id=ss_id,
        version=live_version,
        article_number=new,
    )
    try:
        returned = _put_ss(ctx, body, params, before={"articleNumber": old})
    except WeclappError as exc:
        return _handle_error(ctx, exc, before={"articleNumber": old})
    if isinstance(returned, dict):
        row.weclapp_version = str(returned.get("version") or live_version)
    return _finish(
        ctx,
        "RENUMBERED",
        detail={"before": {"articleNumber": old}, "after": {"articleNumber": new}},
    )


def _attach_articles(ctx: _ApplyCtx, ss_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    ids = list(ctx.row.weclapp_article_ids or [])
    numbers = list(ctx.row.resolved_article_numbers or [])
    for index, article_id in enumerate(ids):
        number = numbers[index] if index < len(numbers) else article_id
        try:
            article = ctx.client.get(f"/article/id/{article_id}")
        except WeclappError as exc:
            mapped = map_weclapp_error(exc)
            if isinstance(mapped, (WeclappTokenInvalid, WeclappLicenceMissing)):
                raise SupplySourceAuthAbort() from exc
            results.append(
                {
                    "article_id": article_id,
                    "article_number": number,
                    "outcome": "GONE" if exc.status_code == 404 else "REJECTED",
                    "error": exc.detail,
                }
            )
            continue
        if not isinstance(article, dict):
            results.append({"article_id": article_id, "outcome": "UNKNOWN"})
            continue
        existing = [
            ref
            for ref in (article.get("supplySources") or [])
            if isinstance(ref, dict)
        ]
        already = any(
            str(ref.get("articleSupplySourceId") or "") == ss_id for ref in existing
        )
        sources = list(existing)
        if not already:
            sources.append({"articleSupplySourceId": ss_id})
        primary = str(article.get("primarySupplySourceId") or "").strip() or ss_id
        version = str(article.get("version") or "")
        body, params = build_article_attach_put(
            article_id=str(article.get("id") or article_id),
            version=version,
            supply_sources=sources,
            primary_supply_source_id=primary,
        )
        try:
            ctx.http_writes += 1
            ctx.client.put(f"/article/id/{article_id}", params=params, json=body)
            results.append(
                {
                    "article_id": article_id,
                    "article_number": number,
                    "outcome": "ATTACHED",
                }
            )
        except WeclappError as exc:
            mapped = map_weclapp_error(exc)
            if isinstance(mapped, (WeclappTokenInvalid, WeclappLicenceMissing)):
                raise SupplySourceAuthAbort() from exc
            results.append(
                {
                    "article_id": article_id,
                    "article_number": number,
                    "outcome": "CONFLICT" if exc.status_code == 409 else "REJECTED",
                    "error": exc.detail,
                }
            )
    return results


def _maybe_write_prices(ctx: _ApplyCtx, ss_id: str, live: Mapping[str, Any]) -> None:
    if ctx.run.preis_eintritt is None:
        return
    ek = _ek(ctx)
    if ek is None:
        return
    current = _current_live_price(live)
    currency_id = _currency_id(ctx.client, ctx.run.einkaufswaehrung, current)
    if not currency_id:
        return
    rebuilt = rebuild_article_prices(
        live, ek=ek, currency_id=currency_id, preis_eintritt=ctx.run.preis_eintritt
    )
    if not _price_fields_changed(live, rebuilt):
        return
    body, params = build_supply_source_put(
        supply_source_id=ss_id,
        version=str(live.get("version") or ""),
        article_prices=rebuilt,
        live_get=live,
    )
    ctx.http_writes += 1
    ctx.client.put(f"/articleSupplySource/id/{ss_id}", params=params, json=body)


def _apply_create(ctx: _ApplyCtx) -> str:
    row = ctx.row
    supplier = ctx.db.get(Supplier, ctx.run.supplier_id)
    if supplier is None:
        return _finish(ctx, "REJECTED", message="Lieferant nicht gefunden.")
    unit_id = supplier.default_unit_id
    if not unit_id:
        return _finish(ctx, "REJECTED", message=MSG_NO_UNIT)
    ss_id = row.created_supply_source_id
    created_now = False
    if not ss_id:
        body = build_supply_source_post(
            supplier_id=supplier.weclapp_party_id,
            article_number=row.supplier_article_number,
            name=row.name or row.supplier_article_number,
            unit_id=unit_id,
        )
        try:
            ctx.http_writes += 1
            created = ctx.client.post("/articleSupplySource", json=body)
        except WeclappError as exc:
            return _handle_error(ctx, exc)
        if not isinstance(created, dict) or not created.get("id"):
            return _finish(ctx, "UNKNOWN", message=MSG_UNKNOWN)
        ss_id = str(created["id"])
        row.created_supply_source_id = ss_id
        row.weclapp_supply_source_id = ss_id
        ctx.db.commit()
        created_now = True
        if ctx.after_create_hook is not None:
            ctx.after_create_hook(ctx)
    article_results = _attach_articles(ctx, ss_id)
    try:
        live = ctx.client.get(f"/articleSupplySource/id/{ss_id}")
        if isinstance(live, dict):
            _maybe_write_prices(ctx, ss_id, live)
            row.weclapp_version = str(live.get("version") or "")
    except WeclappError as exc:
        return _handle_error(ctx, exc)
    failed = [r for r in article_results if r.get("outcome") not in {"ATTACHED"}]
    if failed and any(r.get("outcome") == "ATTACHED" for r in article_results):
        return _finish(
            ctx,
            "UNKNOWN",
            detail={"articles": article_results, "partial": True},
            message="Nur ein Teil der Artikel wurde zugeordnet. Bitte prüfen.",
        )
    if failed:
        return _finish(ctx, "REJECTED", detail={"articles": article_results})
    return _finish(
        ctx,
        "CREATED" if created_now else "ATTACHED",
        detail={"articles": article_results, "supply_source_id": ss_id},
    )


def _apply_attach(ctx: _ApplyCtx) -> str:
    row = ctx.row
    ss_id = row.weclapp_supply_source_id or row.created_supply_source_id
    if not ss_id:
        return _finish(ctx, "GONE")
    live = _get_live_ss(ctx, ss_id)
    if isinstance(live, str):
        return live
    live_version = str(live.get("version") or "")
    if row.weclapp_version and str(row.weclapp_version) != live_version:
        return _finish(ctx, "CONFLICT", message=MSG_CONFLICT)
    article_results = _attach_articles(ctx, ss_id)
    try:
        live = ctx.client.get(f"/articleSupplySource/id/{ss_id}")
        if isinstance(live, dict):
            _maybe_write_prices(ctx, ss_id, live)
    except WeclappError as exc:
        return _handle_error(ctx, exc)
    failed = [r for r in article_results if r.get("outcome") != "ATTACHED"]
    if failed:
        outcome = "UNKNOWN" if any(r.get("outcome") == "ATTACHED" for r in article_results) else "REJECTED"
        return _finish(ctx, outcome, detail={"articles": article_results})
    return _finish(ctx, "ATTACHED", detail={"articles": article_results})


def apply_row(ctx: _ApplyCtx) -> str:
    intent = ctx.row.row_intent
    if intent == "skip":
        return _apply_skip(ctx)
    if intent in {"price_only", "update"}:
        return _apply_price_or_update(ctx, intent=intent or "price_only")
    if intent == "renumber":
        return _apply_renumber(ctx)
    if intent == "create":
        return _apply_create(ctx)
    if intent == "attach":
        return _apply_attach(ctx)
    return _finish(ctx, "REJECTED", message="Unbekannter Vorgang.")


def apply_chunk(
    db: Session,
    run: SupplySourceRun,
    *,
    oid: str,
    actor_name: str,
    client: Any,
    chunk_index: int | None = None,
    after_create_hook: Any = None,
) -> dict[str, Any]:
    if not can_approve(load_rows(db, run.id)):
        raise ValueError(
            "Freigabe nicht möglich: offene Zuordnungen oder fehlende Rabattsätze."
        )
    rows = next_chunk(db, run)
    if not rows:
        run.status = "applied"
        run.applied_at = datetime.now(UTC)
        db.commit()
        return {"applied": 0, "status": run.status}
    index = chunk_index if chunk_index is not None else int(rows[0].chunk_id or 0)
    run.status = "applying"
    db.commit()
    actor = {"oid": oid, "name": actor_name}
    counts: dict[str, int] = {}
    aborted = False
    writes = 0
    for row in rows:
        ctx = _ApplyCtx(db, run, row, client, actor, index)
        ctx.after_create_hook = after_create_hook
        try:
            outcome = apply_row(ctx)
        except SupplySourceAuthAbort:
            aborted = True
            db.refresh(row)
            counts["AUTH"] = counts.get("AUTH", 0) + 1
            break
        counts[outcome] = counts.get(outcome, 0) + 1
        writes += ctx.http_writes
    remaining = pending_rows(db, run)
    if aborted:
        run.status = "failed"
        run.error = MSG_AUTH
    elif remaining:
        run.status = "approved"
    else:
        run.status = "applied"
        run.applied_at = datetime.now(UTC)
    db.commit()
    return {
        "chunk_index": index,
        "applied": sum(counts.values()),
        "outcomes": counts,
        "remaining": len(remaining),
        "aborted": aborted,
        "http_writes": writes,
        "status": run.status,
    }


def enqueue_apply_chunk(
    db: Session,
    run: SupplySourceRun,
    user: Mapping[str, Any],
) -> Any:
    from app.jobs import enqueue

    if not can_approve(load_rows(db, run.id)):
        raise ValueError(
            "Freigabe nicht möglich: offene Zuordnungen oder fehlende Rabattsätze."
        )
    chunk = next_chunk(db, run)
    if not chunk:
        raise ValueError("Keine Zeilen zum Schreiben.")
    if run.approved_at is None:
        run.approved_at = datetime.now(UTC)
        run.approved_by = str(user["oid"])
    existing = [r.chunk_id for r in load_rows(db, run.id) if r.chunk_id is not None]
    chunk_index = (max(existing) + 1) if existing else 0
    for row in chunk:
        row.chunk_id = chunk_index
    run.status = "applying"
    db.flush()
    job = enqueue(
        db,
        "supply_source_apply",
        {
            "run_id": run.id,
            "chunk_index": chunk_index,
            "actor_name": str(user.get("name") or user["oid"]),
        },
        user,
    )
    run.job_id = job.id
    db.commit()
    return job
