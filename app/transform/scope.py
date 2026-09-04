"""Resolve transform scope against a snapshot. Snapshot picks articles, not values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.filter_clauses import filter_clauses
from app.models import ArticleSnapshot, ArticleSnapshotRow
from app.transform.schemas import TransformSpec


@dataclass(frozen=True)
class ScopeCandidate:
    article_number: str
    weclapp_id: str


def resolve_scope(
    db: Session,
    snapshot: ArticleSnapshot,
    spec: TransformSpec | Any,
) -> list[ScopeCandidate]:
    """Return candidates from the snapshot."""
    scope = spec.scope
    if scope.article_numbers is not None:
        numbers = [str(n).strip() for n in scope.article_numbers if str(n).strip()]
        rows = list(
            db.scalars(
                select(ArticleSnapshotRow).where(
                    ArticleSnapshotRow.snapshot_id == snapshot.id,
                    ArticleSnapshotRow.article_number.in_(numbers),
                )
            )
        )
        by_number = {row.article_number: row for row in rows}
        ordered: list[ScopeCandidate] = []
        for number in numbers:
            row = by_number.get(number)
            if row is None:
                ordered.append(ScopeCandidate(article_number=number, weclapp_id=""))
            else:
                ordered.append(
                    ScopeCandidate(
                        article_number=row.article_number,
                        weclapp_id=row.weclapp_id or "",
                    )
                )
        candidates = ordered
    else:
        assert scope.query_filter is not None
        from app.filter_clauses import parse_query_filter

        query_filter = parse_query_filter(scope.query_filter)
        clauses = filter_clauses(db, snapshot, query_filter)
        stmt = (
            select(ArticleSnapshotRow)
            .where(and_(*clauses))
            .order_by(ArticleSnapshotRow.position)
        )
        candidates = [
            ScopeCandidate(
                article_number=row.article_number,
                weclapp_id=row.weclapp_id or "",
            )
            for row in db.scalars(stmt)
        ]

    return candidates
