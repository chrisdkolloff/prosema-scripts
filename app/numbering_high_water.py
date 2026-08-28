"""High-water marks for Prosema article numbers from snapshot + open batches.

Ground truth is the number itself (``MMM.SSS.NNNN``). Category-derived group
codes on snapshot rows are not consulted.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArticleBatch, ArticleBatchRow, ArticleSnapshot, ArticleSnapshotRow
from core.numbering import Scheme


def latest_completed_snapshot(db: Session) -> ArticleSnapshot | None:
    return db.scalars(
        select(ArticleSnapshot)
        .where(ArticleSnapshot.status == "complete")
        .order_by(ArticleSnapshot.created_at.desc())
        .limit(1)
    ).first()


def seed_high_water(
    db: Session,
    *,
    exclude_batch_id: uuid.UUID | None = None,
) -> dict[tuple[str, str], int]:
    """Max running number per (Hauptgruppe, Untergruppe) from snapshot + batches.

    Snapshot rows are included regardless of ``active``. An article number is
    taken forever; deactivating does not release it back into the pool.
    """
    scheme = Scheme()
    pattern = scheme.pattern()
    counters: dict[tuple[str, str], int] = {}

    snapshot = latest_completed_snapshot(db)
    if snapshot is not None:
        # Deliberately no filter on ArticleSnapshotRow.active.
        numbers = db.scalars(
            select(ArticleSnapshotRow.article_number).where(
                ArticleSnapshotRow.snapshot_id == snapshot.id
            )
        )
        for number in numbers:
            match = pattern.match((number or "").strip())
            if match is None:
                continue
            key = (match.group(1), match.group(2))
            counters[key] = max(counters.get(key, 0), int(match.group(3)))

    stmt = (
        select(ArticleBatchRow.proposed_article_number)
        .join(ArticleBatch, ArticleBatchRow.batch_id == ArticleBatch.id)
        .where(ArticleBatch.status != "discarded")
    )
    if exclude_batch_id is not None:
        stmt = stmt.where(ArticleBatch.id != exclude_batch_id)
    for (number,) in db.execute(stmt):
        match = pattern.match((number or "").strip())
        if match is None:
            continue
        key = (match.group(1), match.group(2))
        counters[key] = max(counters.get(key, 0), int(match.group(3)))

    return counters


def assign_proposed_numbers(
    rows: list[ArticleBatchRow],
    reserved: dict[tuple[str, str], int],
) -> None:
    """Assign numbers to rows that have resolved groups and no matching number."""
    scheme = Scheme()
    for row in rows:
        haupt = getattr(row, "_resolved_haupt", None)
        unter = getattr(row, "_resolved_unter", None)
        if haupt is None or unter is None:
            row.proposed_article_number = ""
            continue
        existing = (row.proposed_article_number or "").strip()
        match = scheme.pattern().match(existing)
        if (
            match
            and match.group(1) == haupt.code
            and match.group(2) == unter.code
        ):
            key = (haupt.code, unter.code)
            reserved[key] = max(reserved.get(key, 0), int(match.group(3)))
            continue
        key = (haupt.code, unter.code)
        current = reserved.get(key)
        nxt = scheme.start if current is None else current + scheme.step
        if nxt > scheme.max_running:
            row._group_error = (
                f"Gruppe {haupt.code}.{unter.code} hat das Maximum überschritten."
            )
            row.proposed_article_number = ""
            continue
        reserved[key] = nxt
        row.proposed_article_number = scheme.format(haupt.code, unter.code, nxt)


def register_kept_numbers(
    rows: list[Any],
    reserved: dict[tuple[str, str], int],
    *,
    skip_ids: set[uuid.UUID],
) -> None:
    scheme = Scheme()
    pattern = scheme.pattern()
    for row in rows:
        if row.id in skip_ids:
            continue
        match = pattern.match((row.proposed_article_number or "").strip())
        if match is None:
            continue
        key = (match.group(1), match.group(2))
        reserved[key] = max(reserved.get(key, 0), int(match.group(3)))
