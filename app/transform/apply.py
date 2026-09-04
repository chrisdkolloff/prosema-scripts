"""Apply an approved preview chunk. One weclapp PUT path: update_article."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article_write import ArticleWriteOutcome, update_article
from app.models import TransformChunk, TransformRow, TransformRun
from app.transform.preview import TransformAuthAbort
from app.transform.schemas import MSG_RERUN_NON_IDEM, TransformSpec, spec_has_non_idempotent_ops
from app.transform.summary import chunk_result_summary
from app.weclapp import weclapp_client_for
from core.article_write_fields import CustomAttributeResolver
from scripts.weclapp.client import WeclappClient

CHUNK_SIZE = 200


def changed_rows_ordered(db: Session, run_id: uuid.UUID) -> list[TransformRow]:
    return list(
        db.scalars(
            select(TransformRow)
            .where(
                TransformRow.run_id == run_id,
                TransformRow.row_status == "CHANGED",
            )
            .order_by(TransformRow.article_number, TransformRow.field, TransformRow.id)
        )
    )


def approve_chunk(
    db: Session,
    run: TransformRun,
    *,
    chunk_index: int,
    approver_oid: str,
    selected_row_ids: list[uuid.UUID] | None = None,
) -> TransformChunk:
    """Record that a person approved one slice of CHANGED rows.

    ``selected_row_ids`` is the explicit subset to apply. Unselected rows in
    the slice become DECLINED. When omitted, the whole slice is approved
    (tests and non-UI callers).
    """
    if run.status != "previewed":
        raise ValueError("Nur eine abgeschlossene Vorschau kann bestätigt werden")
    if chunk_index < 0:
        raise ValueError("Ungültiger Abschnitt")
    existing = db.scalars(
        select(TransformChunk).where(
            TransformChunk.run_id == run.id,
            TransformChunk.chunk_index == chunk_index,
        )
    ).first()
    if existing is not None:
        return existing
    if selected_row_ids is None:
        rows = changed_rows_ordered(db, run.id)
        start = chunk_index * CHUNK_SIZE
        slice_rows = rows[start : start + CHUNK_SIZE]
        if not slice_rows:
            raise ValueError("Dieser Abschnitt enthält keine Änderungen")
        chosen = slice_rows
    else:
        claimed: set[uuid.UUID] = set()
        for prior in db.scalars(select(TransformChunk).where(TransformChunk.run_id == run.id)):
            for item in prior.row_ids or []:
                claimed.add(uuid.UUID(str(item)))
        pending = [
            row
            for row in changed_rows_ordered(db, run.id)
            if row.apply_outcome is None and row.id not in claimed
        ]
        slice_rows = pending[:CHUNK_SIZE]
        if not slice_rows:
            raise ValueError("Dieser Abschnitt enthält keine Änderungen")
        selected = set(selected_row_ids)
        slice_ids = {row.id for row in slice_rows}
        unknown = selected - slice_ids
        extra: list[TransformRow] = []
        if unknown:
            extra = list(
                db.scalars(
                    select(TransformRow).where(
                        TransformRow.run_id == run.id,
                        TransformRow.row_status == "DECLINED",
                        TransformRow.apply_outcome.is_(None),
                        TransformRow.id.in_(list(unknown)),
                    )
                )
            )
        extra_ids = {row.id for row in extra}
        if not selected <= (slice_ids | extra_ids):
            raise ValueError("Auswahl gehört nicht zu diesem Abschnitt")
        if not selected:
            raise ValueError("Keine Zeile ausgewählt")
        chosen = [row for row in slice_rows if row.id in selected] + extra
        for row in slice_rows:
            if row.id not in selected:
                row.row_status = "DECLINED"
        for row in extra:
            row.row_status = "CHANGED"
    chunk = TransformChunk(
        run_id=run.id,
        chunk_index=chunk_index,
        row_ids=[str(row.id) for row in chosen],
        approved_by_oid=approver_oid,
        approved_at=datetime.now(UTC),
        status="approved",
        error=None,
    )
    db.add(chunk)
    db.flush()
    return chunk


def preview_run_for_conflicts(
    db: Session,
    source: TransformRun,
    *,
    created_by_oid: str,
) -> TransformRun:
    """New preview run scoped to CONFLICT article numbers. Does not enqueue."""
    numbers = sorted(
        {
            row.article_number
            for row in db.scalars(
                select(TransformRow).where(
                    TransformRow.run_id == source.id,
                    TransformRow.apply_outcome == "CONFLICT",
                )
            )
        }
    )
    if not numbers:
        raise ValueError("Keine Konflikt-Artikel")
    spec = TransformSpec.model_validate(source.spec)
    narrowed = spec.model_copy(
        update={"scope": spec.scope.model_copy(update={"article_numbers": numbers, "query_filter": None})}
    )
    run = TransformRun(
        created_by_oid=created_by_oid,
        snapshot_id=source.snapshot_id,
        spec=narrowed.model_dump(mode="json"),
        status="previewing",
        candidate_count=None,
        error=None,
        case_variants=[],
        word_positions={},
    )
    db.add(run)
    db.flush()
    return run


def _jsonable_detail(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dict, list)):
        return value
    return str(value)


def apply_chunk(
    db: Session,
    chunk: TransformChunk,
    *,
    oid: str,
    actor_name: str | None = None,
    client: WeclappClient | None = None,
) -> dict[str, Any]:
    """Apply unattempted rows in the chunk. Commits after each row."""
    if chunk.status not in {"approved", "applying", "applied", "failed"}:
        raise ValueError(f"Abschnitt-Status {chunk.status!r} erlaubt kein Anwenden")
    run = db.get(TransformRun, chunk.run_id)
    if run is None:
        raise ValueError("Transform-Lauf nicht gefunden")
    is_rerun = chunk.status in {"applying", "applied", "failed"}
    from app.group_assign import is_group_assign_spec, target_category_id_from_row

    group_assign = is_group_assign_spec(run.spec)
    spec = None if group_assign else TransformSpec.model_validate(run.spec)
    refuse_open = is_rerun and spec is not None and spec_has_non_idempotent_ops(spec)
    chunk.status = "applying"
    chunk.error = None
    db.commit()

    wc = client or weclapp_client_for(db, oid)
    resolver = CustomAttributeResolver(wc)
    actor = actor_name or oid
    run_id = str(run.id)
    chunk_id = str(chunk.id)
    versions: dict[str, str] = {}

    ids = [uuid.UUID(str(item)) for item in chunk.row_ids]
    by_id = {
        row.id: row
        for row in db.scalars(select(TransformRow).where(TransformRow.id.in_(ids)))
    }
    ordered = [by_id[i] for i in ids if i in by_id]

    for row in ordered:
        db.refresh(row)
        if row.apply_outcome is not None:
            continue
        if refuse_open:
            row.apply_outcome = "REFUSED"
            row.apply_detail = MSG_RERUN_NON_IDEM
            db.commit()
            continue
        expected = versions.get(row.weclapp_id) or row.version_at_preview
        if group_assign:
            from app.article_write import update_article_category

            result = update_article_category(
                db=db,
                client=wc,
                article_id=row.weclapp_id,
                category_id=target_category_id_from_row(row),
                actor_oid=oid,
                actor_name=actor,
                allow_live=True,
                expected_version=expected,
                transform_run_id=run_id,
                transform_chunk_id=chunk_id,
            )
        else:
            result = update_article(
                db=db,
                client=wc,
                resolver=resolver,
                article_id=row.weclapp_id,
                changes={row.field: row.new_value},
                actor_oid=oid,
                actor_name=actor,
                expected_version=expected,
                transform_run_id=run_id,
                transform_chunk_id=chunk_id,
            )
        if result.outcome is ArticleWriteOutcome.AUTH:
            raise TransformAuthAbort(result.message or str(result.outcome))
        row.apply_outcome = result.outcome.value
        row.apply_detail = _jsonable_detail(result.weclapp_detail)
        if result.weclapp_detail is None and result.message:
            row.apply_detail = result.message
        row.apply_version_seen = result.version_before
        if result.version_after:
            versions[row.weclapp_id] = result.version_after
        elif result.version_before:
            versions[row.weclapp_id] = result.version_before
        db.commit()

    chunk.status = "applied"
    chunk.error = None
    db.commit()
    db.refresh(chunk)
    summary = chunk_result_summary(db, chunk)
    return {"chunk_id": chunk_id, "summary": summary}


def fail_chunk(db: Session, chunk: TransformChunk, message: str) -> None:
    chunk.status = "failed"
    chunk.error = message
    db.commit()


def start_transform_apply(
    db: Session,
    user: dict[str, Any],
    *,
    chunk_id: uuid.UUID,
) -> tuple[TransformChunk, Any]:
    from app.jobs import enqueue

    chunk = db.get(TransformChunk, chunk_id)
    if chunk is None:
        raise ValueError("Abschnitt nicht gefunden")
    job = enqueue(
        db,
        "article_transform_apply",
        {"transform_chunk_id": str(chunk.id), "actor_name": str(user.get("name") or user["oid"])},
        user,
    )
    return chunk, job
