"""Read-only weclapp supply-source index build."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Supplier,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
    WeclappSupplySourcePrice,
)
from scripts.weclapp.master_columns import _custom_attributes_by_label

logger = logging.getLogger(__name__)

DATENSTAND_HINWEIS = "Beginn der Abfrage, nicht Abschluss"


class DuplicateSupplySourceError(ValueError):
    """weclapp-side invariant broken: two SS for the same supplier + SAN."""


class RequestCountingClient:
    """Count GET requests while delegating to a WeclappClient."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.get_requests = 0

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        self.get_requests += 1
        return self._inner.get(path, params=params)

    def iter_pages(
        self,
        entity: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int | None = None,
    ):
        entity = entity.strip("/")
        page_size = page_size or getattr(self._inner, "PAGE_SIZE", 1000)
        page = 1
        query = dict(params or {})
        query["pageSize"] = page_size
        while True:
            query["page"] = page
            payload = self.get(f"/{entity}", params=query)
            if not isinstance(payload, dict):
                break
            rows = payload.get("result") or []
            if not rows:
                break
            yield from rows
            if len(rows) < page_size:
                break
            page += 1


def _parse_decimal(raw: object) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, Decimal):
        return raw
    try:
        return Decimal(str(raw).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _epoch_ms(raw: object) -> datetime | None:
    if raw is None or raw == "":
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _text(raw: object) -> str | None:
    value = str(raw or "").strip()
    return value or None


def duplicate_supply_source_message(
    groups: list[tuple[str, str, list[str]]],
    *,
    supplier_numbers: dict[str, str],
) -> str:
    parts: list[str] = []
    for party_id, san, ss_ids in groups:
        number = supplier_numbers.get(party_id) or party_id
        parts.append(
            f"Lieferant {number}, Lieferantenartikelnummer {san} "
            f"(weclapp-IDs {', '.join(ss_ids)})"
        )
    return (
        "Doppelte Bezugsquellen für denselben Lieferanten und dieselbe "
        "Lieferantenartikelnummer. Das ist ein Datenproblem in weclapp, "
        "kein Programmfehler. Bitte klären: " + "; ".join(parts) + "."
    )


def find_duplicate_supply_sources(
    supply_sources: list[dict[str, Any]],
) -> list[tuple[str, str, list[str]]]:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in supply_sources:
        party = str(row.get("supplierId") or "").strip()
        san = str(row.get("articleNumber") or "").strip()
        ss_id = str(row.get("id") or "").strip()
        if not party or not san or not ss_id:
            continue
        grouped[(party, san)].append(ss_id)
    return [
        (party, san, ids)
        for (party, san), ids in grouped.items()
        if len(ids) > 1
    ]


def _attribute_labels(client: RequestCountingClient) -> dict[str, str]:
    labels: dict[str, str] = {}
    for definition in client.iter_pages("customAttributeDefinition"):
        attr_id = str(definition.get("id") or "").strip()
        label = str(
            definition.get("label") or definition.get("attributeKey") or attr_id
        ).strip()
        if attr_id and label:
            labels[attr_id] = label
    return labels


def _currency_codes(client: RequestCountingClient) -> dict[str, str]:
    codes: dict[str, str] = {}
    for row in client.iter_pages("currency"):
        cid = str(row.get("id") or "").strip()
        code = str(
            row.get("name") or row.get("isoCode") or row.get("currencyName") or ""
        ).strip()
        if not code:
            code = str(row.get("abbreviation") or "").strip()
        if cid:
            codes[cid] = code or cid
    return codes


def _party_numbers(
    client: RequestCountingClient,
    party_ids: set[str],
) -> dict[str, str]:
    numbers: dict[str, str] = {}
    for party_id in sorted(party_ids):
        if not party_id:
            continue
        row = client.get(f"/party/id/{party_id}")
        if not isinstance(row, dict):
            raise ValueError(f"Lieferant (Party {party_id}) nicht lesbar.")
        numbers[party_id] = str(row.get("supplierNumber") or "").strip()
    return numbers


def _insert_on_conflict(
    db: Session,
    model,
    rows: list[dict[str, Any]],
    *,
    pk: str,
    update_cols: list[str],
    batch_size: int = 400,
) -> None:
    if not rows:
        return
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        stmt = insert(model).values(chunk)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[pk],
                set_={col: getattr(stmt.excluded, col) for col in update_cols},
            )
        )


def _insert_chunks(
    db: Session,
    model,
    rows: list[dict[str, Any]],
    *,
    batch_size: int = 400,
) -> None:
    if not rows:
        return
    for start in range(0, len(rows), batch_size):
        db.execute(insert(model).values(rows[start : start + batch_size]))


def pull_supply_source_index(
    db: Session,
    *,
    oid: str,
    supplier_id: int | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Fetch articles + supply sources (read-only) and rebuild the local mirror.

    ``datenstand`` is the pull START time, not completion.
    """
    from app.weclapp import weclapp_client_for

    datenstand = datetime.now(UTC)
    wall_start = time.perf_counter()

    filter_party_id: str | None = None
    if supplier_id is not None:
        supplier = db.get(Supplier, int(supplier_id))
        if supplier is None or supplier.deleted_at is not None:
            raise ValueError(f"Lieferant {supplier_id} nicht gefunden.")
        filter_party_id = supplier.weclapp_party_id

    if client is None:
        client = weclapp_client_for(db, oid)
    counted = RequestCountingClient(client)

    attr_labels = _attribute_labels(counted)
    articles = list(counted.iter_pages("article"))
    ss_params = (
        {"supplierId-eq": filter_party_id} if filter_party_id else None
    )
    supply_sources = list(
        counted.iter_pages("articleSupplySource", params=ss_params)
    )
    currency_codes = _currency_codes(counted)

    party_ids = {
        str(row.get("supplierId") or "").strip()
        for row in supply_sources
        if row.get("supplierId")
    }
    supplier_numbers = _party_numbers(counted, party_ids)

    duplicates = find_duplicate_supply_sources(supply_sources)
    if duplicates:
        raise DuplicateSupplySourceError(
            duplicate_supply_source_message(
                duplicates, supplier_numbers=supplier_numbers
            )
        )

    seen_article_ids: set[str] = set()
    article_rows: list[dict[str, Any]] = []
    for article in articles:
        aid = str(article.get("id") or "").strip()
        if not aid:
            continue
        seen_article_ids.add(aid)
        attrs = _custom_attributes_by_label(article, attr_labels)
        article_rows.append(
            {
                "weclapp_article_id": aid,
                "article_number": str(article.get("articleNumber") or "").strip(),
                "name": _text(article.get("name")),
                "ean": _text(article.get("ean")),
                "rabattcode": _text(attrs.get("Rabattcode")),
                "weclapp_version": str(article.get("version") or ""),
                "last_seen_at": datenstand,
                "missing_since": None,
            }
        )

    seen_ss_ids: set[str] = set()
    ss_rows: list[dict[str, Any]] = []
    ss_by_id: dict[str, dict[str, Any]] = {}
    price_rows: list[dict[str, Any]] = []
    for supply in supply_sources:
        ss_id = str(supply.get("id") or "").strip()
        if not ss_id:
            continue
        party = str(supply.get("supplierId") or "").strip()
        seen_ss_ids.add(ss_id)
        ss_row = {
                "weclapp_id": ss_id,
                "supplier_party_id": party,
                "supplier_number": supplier_numbers.get(party) or "",
                "supplier_article_number": str(
                    supply.get("articleNumber") or ""
                ).strip(),
                "name": _text(supply.get("name")),
                "unit_id": _text(supply.get("unitId")),
                "tax_rate_type": _text(supply.get("taxRateType")),
                "ean": _text(supply.get("ean")),
                "min_purchase_qty": _parse_decimal(
                    supply.get("minimumPurchaseQuantity")
                ),
                "fixed_purchase_qty": _parse_decimal(
                    supply.get("fixedPurchaseQuantity")
                ),
                "procurement_lead_days": (
                    int(supply["procurementLeadDays"])
                    if supply.get("procurementLeadDays") not in (None, "")
                    else None
                ),
                "weclapp_version": str(supply.get("version") or ""),
                "last_seen_at": datenstand,
                "missing_since": None,
            }
        ss_rows.append(ss_row)
        ss_by_id[ss_id] = ss_row
        for price in supply.get("articlePrices") or []:
            if not isinstance(price, dict):
                continue
            currency_id = _text(price.get("currencyId"))
            price_rows.append(
                {
                    "supply_source_weclapp_id": ss_id,
                    "weclapp_price_id": _text(price.get("id")),
                    "price": _parse_decimal(price.get("price")),
                    "currency_id": currency_id,
                    "currency_code": (
                        currency_codes.get(currency_id, currency_id)
                        if currency_id
                        else None
                    ),
                    "start_date": _epoch_ms(price.get("startDate")),
                    "end_date": _epoch_ms(price.get("endDate")),
                    "reduction_additions": price.get("reductionAdditions"),
                }
            )

    link_rows: list[dict[str, Any]] = []
    seen_link_keys: set[tuple[str, str]] = set()
    for article in articles:
        aid = str(article.get("id") or "").strip()
        article_number = str(article.get("articleNumber") or "").strip()
        primary = str(article.get("primarySupplySourceId") or "").strip()
        for ref in article.get("supplySources") or []:
            if not isinstance(ref, dict):
                continue
            ss_id = str(
                ref.get("articleSupplySourceId") or ref.get("id") or ""
            ).strip()
            if not ss_id or ss_id not in seen_ss_ids:
                continue
            key = (ss_id, aid)
            if key in seen_link_keys:
                continue
            seen_link_keys.add(key)
            parent = ss_by_id.get(ss_id)
            party = parent["supplier_party_id"] if parent else ""
            position = ref.get("positionNumber")
            link_rows.append(
                {
                    "supply_source_weclapp_id": ss_id,
                    "weclapp_article_id": aid,
                    "article_number": article_number,
                    "supplier_party_id": party,
                    "position_number": (
                        int(position) if position not in (None, "") else None
                    ),
                    "is_primary": bool(primary) and ss_id == primary,
                }
            )

    _insert_on_conflict(
        db,
        WeclappArticle,
        article_rows,
        pk="weclapp_article_id",
        update_cols=[
            "article_number",
            "name",
            "ean",
            "rabattcode",
            "weclapp_version",
            "last_seen_at",
            "missing_since",
        ],
    )
    _insert_on_conflict(
        db,
        WeclappSupplySource,
        ss_rows,
        pk="weclapp_id",
        update_cols=[
            "supplier_party_id",
            "supplier_number",
            "supplier_article_number",
            "name",
            "unit_id",
            "tax_rate_type",
            "ean",
            "min_purchase_qty",
            "fixed_purchase_qty",
            "procurement_lead_days",
            "weclapp_version",
            "last_seen_at",
            "missing_since",
        ],
    )

    seen_list = list(seen_ss_ids)
    if seen_list:
        for start in range(0, len(seen_list), 400):
            chunk = seen_list[start : start + 400]
            db.execute(
                delete(WeclappSupplySourcePrice).where(
                    WeclappSupplySourcePrice.supply_source_weclapp_id.in_(chunk)
                )
            )
            db.execute(
                delete(WeclappSupplySourceLink).where(
                    WeclappSupplySourceLink.supply_source_weclapp_id.in_(chunk)
                )
            )
    elif filter_party_id is None:
        db.execute(delete(WeclappSupplySourcePrice))
        db.execute(delete(WeclappSupplySourceLink))

    _insert_chunks(db, WeclappSupplySourcePrice, price_rows)
    _insert_chunks(db, WeclappSupplySourceLink, link_rows)

    if filter_party_id is None:
        if seen_article_ids:
            db.execute(
                update(WeclappArticle)
                .where(WeclappArticle.weclapp_article_id.not_in(seen_article_ids))
                .where(WeclappArticle.missing_since.is_(None))
                .values(missing_since=datenstand)
            )
        if seen_ss_ids:
            db.execute(
                update(WeclappSupplySource)
                .where(WeclappSupplySource.weclapp_id.not_in(seen_ss_ids))
                .where(WeclappSupplySource.missing_since.is_(None))
                .values(missing_since=datenstand)
            )
    elif seen_ss_ids:
        db.execute(
            update(WeclappSupplySource)
            .where(WeclappSupplySource.supplier_party_id == filter_party_id)
            .where(WeclappSupplySource.weclapp_id.not_in(seen_ss_ids))
            .where(WeclappSupplySource.missing_since.is_(None))
            .values(missing_since=datenstand)
        )
    else:
        db.execute(
            update(WeclappSupplySource)
            .where(WeclappSupplySource.supplier_party_id == filter_party_id)
            .where(WeclappSupplySource.missing_since.is_(None))
            .values(missing_since=datenstand)
        )

    db.execute(
        text(
            """
            INSERT INTO supplier_article_aliases (
                supplier_id,
                supplier_article_number,
                article_number,
                weclapp_article_id,
                source
            )
            SELECT
                s.id,
                ss.supplier_article_number,
                l.article_number,
                l.weclapp_article_id,
                'supply_source'
            FROM weclapp_supply_source_links l
            JOIN weclapp_supply_sources ss
              ON ss.weclapp_id = l.supply_source_weclapp_id
            JOIN suppliers s
              ON s.weclapp_party_id = l.supplier_party_id
            ON CONFLICT (supplier_id, supplier_article_number, article_number)
            DO NOTHING
            """
        )
    )

    db.commit()
    elapsed = time.perf_counter() - wall_start
    primary_links = sum(1 for row in link_rows if row["is_primary"])
    return {
        "datenstand": datenstand.isoformat(),
        "datenstand_hinweis": DATENSTAND_HINWEIS,
        "article_count": len(article_rows),
        "supply_source_count": len(ss_rows),
        "link_count": len(link_rows),
        "primary_link_count": primary_links,
        "price_count": len(price_rows),
        "duplicate_groups": 0,
        "get_requests": counted.get_requests,
        "elapsed_seconds": round(elapsed, 3),
        "filtered_party_id": filter_party_id,
    }


def enqueue_supply_source_index(
    db: Session,
    user: dict[str, Any],
    *,
    supplier_id: int | None = None,
):
    from app.jobs import enqueue

    payload: dict[str, Any] = {}
    if supplier_id is not None:
        payload["supplier_id"] = int(supplier_id)
    return enqueue(db, "weclapp_supply_source_index", payload, user)
