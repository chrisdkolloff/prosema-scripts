"""Artikel-Übersicht: snapshot pull, filtering, grid config, Excel export."""

from __future__ import annotations

import io
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.batches import JSPREADSHEET_CE_VERSION, JSUITES_VERSION
from app.config import settings
from app.models import ArticleSnapshot, ArticleSnapshotRow, Job
from core.article_flatten import flatten_articles

logger = logging.getLogger(__name__)

ZURICH = ZoneInfo("Europe/Zurich")
GRID_PAGE_SIZE = 250
RETENTION_COUNT = 20
EXCEL_MAX_ROWS = 50_000

ARTICLE_NUMBER_FIELD = "Prosema Artikelnummer"
KURZTEXT_FIELD = "PROSEMA Kurztext"

TEXT_EXCEL_COLUMNS = frozenset(
    {
        ARTICLE_NUMBER_FIELD,
        "Hauptgruppe",
        "Untergruppe",
        "GTIN (EAN-Nummer)",
        "Lieferantenartikelnummer",
    }
)

_PRICE_RE = re.compile(r"preis|€", re.IGNORECASE)


@dataclass
class SnapshotFilters:
    query: str = ""
    hauptgruppe: str = ""
    untergruppe: str = ""
    nur_aktive: bool = True
    page: int = 1


def format_swiss_number(value: int) -> str:
    return f"{value:,}".replace(",", "\u202f")


def format_snapshot_timestamp(when: datetime) -> str:
    local = when.astimezone(ZURICH)
    return local.strftime("%d.%m.%Y, %H:%M Uhr")


def excel_filename_timestamp(when: datetime) -> str:
    local = when.astimezone(ZURICH)
    return local.strftime("%Y-%m-%d_%H%M")


def running_snapshot(db: Session) -> ArticleSnapshot | None:
    return db.scalars(
        select(ArticleSnapshot).where(ArticleSnapshot.status == "running").limit(1)
    ).first()


def list_snapshots(db: Session, *, tenant: str | None = None) -> list[ArticleSnapshot]:
    tenant = tenant or settings.weclapp_tenant.strip()
    return list(
        db.scalars(
            select(ArticleSnapshot)
            .where(ArticleSnapshot.weclapp_tenant == tenant)
            .order_by(ArticleSnapshot.created_at.desc())
        )
    )


def _base_row_query(snapshot_id: uuid.UUID, filters: SnapshotFilters):
    stmt = select(ArticleSnapshotRow).where(ArticleSnapshotRow.snapshot_id == snapshot_id)
    if filters.nur_aktive:
        stmt = stmt.where(ArticleSnapshotRow.active.is_(True))
    if filters.hauptgruppe:
        stmt = stmt.where(ArticleSnapshotRow.hauptgruppe_code == filters.hauptgruppe)
    if filters.untergruppe:
        stmt = stmt.where(ArticleSnapshotRow.untergruppe_code == filters.untergruppe)
    needle = filters.query.strip().lower()
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                func.lower(ArticleSnapshotRow.article_number).like(pattern),
                func.lower(ArticleSnapshotRow.article_name).like(pattern),
            )
        )
    return stmt


def count_filtered_rows(db: Session, snapshot_id: uuid.UUID, filters: SnapshotFilters) -> int:
    stmt = select(func.count()).select_from(_base_row_query(snapshot_id, filters).subquery())
    return int(db.scalar(stmt) or 0)


def fetch_filtered_rows(
    db: Session,
    snapshot_id: uuid.UUID,
    filters: SnapshotFilters,
) -> tuple[list[ArticleSnapshotRow], int, int]:
    total = count_filtered_rows(db, snapshot_id, filters)
    page = max(1, filters.page)
    start = (page - 1) * GRID_PAGE_SIZE
    stmt = (
        _base_row_query(snapshot_id, filters)
        .order_by(ArticleSnapshotRow.position)
        .offset(start)
        .limit(GRID_PAGE_SIZE)
    )
    rows = list(db.scalars(stmt))
    pages = max(1, (total + GRID_PAGE_SIZE - 1) // GRID_PAGE_SIZE) if total else 1
    return rows, total, pages


def fetch_all_filtered_rows(
    db: Session,
    snapshot_id: uuid.UUID,
    filters: SnapshotFilters,
) -> list[ArticleSnapshotRow]:
    stmt = _base_row_query(snapshot_id, filters).order_by(ArticleSnapshotRow.position)
    return list(db.scalars(stmt))


def distinct_hauptgruppen(db: Session, snapshot_id: uuid.UUID) -> list[str]:
    stmt = (
        select(ArticleSnapshotRow.hauptgruppe_code)
        .where(
            ArticleSnapshotRow.snapshot_id == snapshot_id,
            ArticleSnapshotRow.hauptgruppe_code != "",
        )
        .distinct()
        .order_by(ArticleSnapshotRow.hauptgruppe_code)
    )
    return [row[0] for row in db.execute(stmt).all()]


def distinct_untergruppen(
    db: Session,
    snapshot_id: uuid.UUID,
    *,
    hauptgruppe: str = "",
) -> list[str]:
    stmt = select(ArticleSnapshotRow.untergruppe_code).where(
        ArticleSnapshotRow.snapshot_id == snapshot_id,
        ArticleSnapshotRow.untergruppe_code != "",
    )
    if hauptgruppe:
        stmt = stmt.where(ArticleSnapshotRow.hauptgruppe_code == hauptgruppe)
    stmt = stmt.distinct().order_by(ArticleSnapshotRow.untergruppe_code)
    return [row[0] for row in db.execute(stmt).all()]


def _freeze_column_count(columns: list[dict[str, Any]]) -> int:
    keys = [col.get("key", "") for col in columns]
    count = 0
    for target in (ARTICLE_NUMBER_FIELD, KURZTEXT_FIELD):
        if target in keys:
            count += 1
    return max(count, 1)


def build_grid_config(
    snapshot: ArticleSnapshot,
    rows: list[ArticleSnapshotRow],
) -> dict[str, Any]:
    columns = snapshot.columns or []
    jss_columns: list[dict[str, Any]] = []
    keys: list[str] = []
    for col in columns:
        key = str(col.get("key", ""))
        keys.append(key)
        jss_columns.append(
            {
                "type": "text",
                "title": str(col.get("title", key)),
                "width": int(col.get("width", 140)),
                "readOnly": True,
                "name": key,
            }
        )
    data = [[row.data.get(key, "") if isinstance(row.data, dict) else "" for key in keys] for row in rows]
    return {
        "editable": False,
        "parseFormulas": False,
        "freezeColumns": _freeze_column_count(columns),
        "columns": jss_columns,
        "data": data,
        "fields": keys,
    }


def _parse_price(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace(" ", "").replace("'", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _is_price_column(key: str) -> bool:
    return bool(_PRICE_RE.search(key))


def build_excel_workbook(
    snapshot: ArticleSnapshot,
    rows: list[ArticleSnapshotRow],
    filters: SnapshotFilters,
) -> Workbook:
    columns = snapshot.columns or []
    keys = [str(col.get("key", "")) for col in columns]
    wb = Workbook()
    ws = wb.active
    ws.title = "Artikel"

    for col_idx, key in enumerate(keys, start=1):
        ws.cell(row=1, column=col_idx, value=key)

    for row_idx, row in enumerate(rows, start=2):
        data = row.data if isinstance(row.data, dict) else {}
        for col_idx, key in enumerate(keys, start=1):
            raw = data.get(key, "")
            cell = ws.cell(row=row_idx, column=col_idx)
            if key in TEXT_EXCEL_COLUMNS:
                text = str(raw) if raw is not None else ""
                cell.value = text
                cell.number_format = "@"
            elif _is_price_column(key):
                number = _parse_price(str(raw))
                if number is not None:
                    cell.value = number
                    cell.number_format = "#,##0.00"
                else:
                    cell.value = str(raw) if raw else None
            else:
                cell.value = str(raw) if raw is not None and raw != "" else None

    if keys:
        ws.freeze_panes = "A2"
        last_col = get_column_letter(len(keys))
        ws.auto_filter.ref = f"A1:{last_col}{max(1, len(rows) + 1)}"

    meta = wb.create_sheet("Abfrage")
    meta.append(["Merkmal", "Wert"])
    meta.append(["Stand", format_snapshot_timestamp(snapshot.created_at)])
    meta.append(["Tenant", snapshot.weclapp_tenant])
    meta.append(["Zeilen im Snapshot", snapshot.row_count or 0])
    meta.append(["Zeilen in dieser Datei", len(rows)])
    meta.append(["Suche", filters.query or "(keine)"])
    meta.append(["Hauptgruppe", filters.hauptgruppe or "(alle)"])
    meta.append(["Untergruppe", filters.untergruppe or "(alle)"])
    meta.append(["Nur aktive Artikel", "Ja" if filters.nur_aktive else "Nein"])
    return wb


def excel_bytes(
    snapshot: ArticleSnapshot,
    rows: list[ArticleSnapshotRow],
    filters: SnapshotFilters,
) -> bytes:
    wb = build_excel_workbook(snapshot, rows, filters)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def apply_retention(db: Session, *, tenant: str) -> list[uuid.UUID]:
    """Keep the newest RETENTION_COUNT snapshots per tenant; delete older ones."""
    snapshots = list(
        db.scalars(
            select(ArticleSnapshot)
            .where(
                ArticleSnapshot.weclapp_tenant == tenant,
                ArticleSnapshot.status == "complete",
            )
            .order_by(ArticleSnapshot.created_at.asc(), ArticleSnapshot.id.asc())
        )
    )
    if len(snapshots) <= RETENTION_COUNT:
        return []
    to_delete = snapshots[: len(snapshots) - RETENTION_COUNT]
    ids = [item.id for item in to_delete]
    db.execute(delete(ArticleSnapshot).where(ArticleSnapshot.id.in_(ids)))
    for item in to_delete:
        logger.info(
            "snapshot retention: deleted snapshot %s (tenant=%s, created=%s, rows=%s)",
            item.id,
            tenant,
            item.created_at.isoformat(),
            item.row_count,
        )
    return ids


def pull_snapshot_rows(
    db: Session,
    snapshot: ArticleSnapshot,
    *,
    oid: str,
) -> dict[str, Any]:
    """Fetch from weclapp (read-only) and persist rows in one transaction."""
    from app.weclapp import weclapp_client_for

    client = weclapp_client_for(db, oid)
    articles = list(client.iter_pages("article"))
    data_rows, indexed, columns = flatten_articles(client, articles)

    db.execute(
        delete(ArticleSnapshotRow).where(ArticleSnapshotRow.snapshot_id == snapshot.id)
    )
    for position, (data, fields) in enumerate(zip(data_rows, indexed, strict=True)):
        db.add(
            ArticleSnapshotRow(
                snapshot_id=snapshot.id,
                position=position,
                data=data,
                article_number=fields["article_number"],
                article_name=fields["article_name"],
                hauptgruppe_code=fields["hauptgruppe_code"],
                untergruppe_code=fields["untergruppe_code"],
                active=fields["active"],
                weclapp_id=fields["weclapp_id"],
                weclapp_version=fields["weclapp_version"],
            )
        )

    snapshot.columns = columns
    snapshot.row_count = len(data_rows)
    snapshot.status = "complete"
    snapshot.error = None
    deleted = apply_retention(db, tenant=snapshot.weclapp_tenant)
    db.commit()
    return {"row_count": len(data_rows), "deleted_snapshots": [str(i) for i in deleted]}


def fail_snapshot(db: Session, snapshot: ArticleSnapshot, message: str) -> None:
    db.execute(
        delete(ArticleSnapshotRow).where(ArticleSnapshotRow.snapshot_id == snapshot.id)
    )
    snapshot.status = "failed"
    snapshot.error = message
    snapshot.row_count = None
    db.commit()


def create_snapshot_pull(
    db: Session,
    user: dict[str, Any],
) -> tuple[ArticleSnapshot, Job] | ArticleSnapshot:
    """Enqueue a pull or return the snapshot that is already running."""
    tenant = settings.weclapp_tenant.strip()
    existing = running_snapshot(db)
    if existing is not None:
        return existing

    from app.jobs import enqueue

    snapshot = ArticleSnapshot(
        status="running",
        created_by_oid=user["oid"],
        created_by_name=user["name"],
        weclapp_tenant=tenant,
    )
    db.add(snapshot)
    db.flush()

    job = enqueue(
        db,
        "weclapp_article_snapshot",
        {"snapshot_id": str(snapshot.id)},
        user,
    )
    snapshot.job_id = job.id
    db.commit()
    db.refresh(snapshot)
    return snapshot, job
