"""Preview a transform: live GET only, never PUT."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article_write import live_field_value
from app.models import ArticleSnapshot, ArticleSnapshotRow, TransformRow, TransformRun
from app.transform.engine import apply_operations, operations_fired
from app.transform.live_fetch import fetch_live_articles
from app.transform.schemas import TransformSpec
from app.transform.scope import resolve_scope
from app.transform.summary import preview_summary
from app.transform.word_position import WordPositionCollector
from app.weclapp import (
    WeclappLicenceMissing,
    WeclappTokenInvalid,
    map_weclapp_error,
    weclapp_client_for,
)
from core.article_write_fields import CustomAttributeResolver, write_field
from scripts.weclapp.client import WeclappClient, WeclappError


class TransformAuthAbort(Exception):
    """Licence/token failure: abort the whole preview, not one row."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _auth_from_error(exc: WeclappError) -> TransformAuthAbort | None:
    mapped = map_weclapp_error(exc)
    if isinstance(mapped, (WeclappTokenInvalid, WeclappLicenceMissing)):
        return TransformAuthAbort(str(mapped))
    return None


def _snapshot_would_change(data: dict[str, Any] | None, spec: TransformSpec) -> bool:
    payload = data if isinstance(data, dict) else {}
    for key in spec.fields:
        field = write_field(key)
        raw = payload.get(key)
        old = "" if raw is None else str(raw)
        try:
            if apply_operations(old, spec.operations, field.value_kind) != old:
                return True
        except ValueError:
            return True
    return False


def _snapshot_rows_by_number(
    db: Session, snapshot_id: uuid.UUID, numbers: list[str]
) -> dict[str, ArticleSnapshotRow]:
    if not numbers:
        return {}
    rows = db.scalars(
        select(ArticleSnapshotRow).where(
            ArticleSnapshotRow.snapshot_id == snapshot_id,
            ArticleSnapshotRow.article_number.in_(numbers),
        )
    )
    return {row.article_number: row for row in rows}


def _existing_article_numbers(db: Session, run_id: uuid.UUID) -> set[str]:
    return set(
        db.scalars(
            select(TransformRow.article_number).where(TransformRow.run_id == run_id)
        )
    )


def _add_gone(
    db: Session,
    run: TransformRun,
    *,
    article_number: str,
    weclapp_id: str,
    field: str,
) -> None:
    db.add(
        TransformRow(
            run_id=run.id,
            article_number=article_number,
            weclapp_id=weclapp_id,
            version_at_preview=None,
            field=field,
            old_value="",
            new_value="",
            operations_fired=[],
            row_status="GONE",
        )
    )


def run_preview(
    db: Session,
    run: TransformRun,
    *,
    oid: str,
    client: WeclappClient | None = None,
) -> dict[str, Any]:
    snapshot = db.get(ArticleSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.status != "complete":
        raise ValueError("Snapshot nicht gefunden oder nicht abgeschlossen")
    from app.group_assign import is_group_assign_spec, run_group_assign_preview

    if is_group_assign_spec(run.spec):
        return run_group_assign_preview(db, run, oid=oid, client=client)
    spec = TransformSpec.model_validate(run.spec)
    candidates = resolve_scope(db, snapshot, spec)
    rows_by_number = _snapshot_rows_by_number(
        db, snapshot.id, [c.article_number for c in candidates]
    )
    live = []
    for candidate in candidates:
        snap_row = rows_by_number.get(candidate.article_number)
        if snap_row is not None and not _snapshot_would_change(snap_row.data, spec):
            continue
        live.append(candidate)
    done = _existing_article_numbers(db, run.id)
    live = [c for c in live if c.article_number not in done]
    run.candidate_count = len(live) + len(done)
    if not live:
        run.status = "previewed"
        run.error = None
        if not done:
            run.case_variants = []
            run.word_positions = WordPositionCollector(spec.operations).payload()
        db.flush()
        summary = preview_summary(run, changed_rows=None if done else 0)
        return {
            "candidate_count": len(done),
            "changed_rows": sum(1 for row in (run.rows or []) if row.row_status == "CHANGED"),
            "word_positions": run.word_positions,
            "summary": summary,
        }

    wc = client or weclapp_client_for(db, oid)
    resolver = CustomAttributeResolver(wc)
    try:
        resolver.load()
    except WeclappError as exc:
        abort = _auth_from_error(exc)
        if abort is not None:
            raise abort from exc
        raise

    try:
        fetched = fetch_live_articles(wc, live)
    except WeclappError as exc:
        abort = _auth_from_error(exc)
        if abort is not None:
            raise abort from exc
        raise

    changed = 0
    positions = WordPositionCollector(spec.operations)
    gone_field = spec.fields[0]
    for candidate in live:
        weclapp_id = candidate.weclapp_id
        if not weclapp_id or weclapp_id in fetched.gone_ids:
            _add_gone(
                db,
                run,
                article_number=candidate.article_number,
                weclapp_id=weclapp_id or "",
                field=gone_field,
            )
            db.commit()
            continue
        article = fetched.articles.get(weclapp_id)
        if article is None:
            _add_gone(
                db,
                run,
                article_number=candidate.article_number,
                weclapp_id=weclapp_id,
                field=gone_field,
            )
            db.commit()
            continue

        if not isinstance(article, dict):
            raise WeclappError("weclapp GET /article did not return an object")
        version = str(article.get("version") or "")
        number = str(article.get("articleNumber") or candidate.article_number)
        for snapshot_key in spec.fields:
            field = write_field(snapshot_key)
            old = ""
            try:
                old = live_field_value(article, snapshot_key, resolver)
                new = apply_operations(old, spec.operations, field.value_kind)
                fired = operations_fired(old, spec.operations, field.value_kind)
            except ValueError:
                db.add(
                    TransformRow(
                        run_id=run.id,
                        article_number=number,
                        weclapp_id=weclapp_id,
                        version_at_preview=version or None,
                        field=snapshot_key,
                        old_value=old,
                        new_value="",
                        operations_fired=[],
                        row_status="REFUSED",
                    )
                )
                continue
            status = "CHANGED" if new != old else "UNCHANGED"
            if status == "CHANGED":
                changed += 1
            inside = positions.observe_row(old, field.value_kind)
            db.add(
                TransformRow(
                    run_id=run.id,
                    article_number=number,
                    weclapp_id=weclapp_id,
                    version_at_preview=version or None,
                    field=snapshot_key,
                    old_value=old,
                    new_value=new,
                    operations_fired=fired,
                    row_status=status,
                    inside_compound=inside,
                )
            )
        db.commit()

    run.status = "previewed"
    run.error = None
    run.case_variants = []
    run.word_positions = positions.payload()
    db.flush()
    summary = preview_summary(run, changed_rows=changed)
    return {
        "candidate_count": len(live) + len(done),
        "changed_rows": changed,
        "word_positions": run.word_positions,
        "summary": summary,
    }


def fail_preview(db: Session, run: TransformRun, message: str) -> None:
    run.status = "failed"
    run.error = message
    db.commit()


def start_transform_preview(
    db: Session,
    user: dict[str, Any],
    *,
    snapshot_id: uuid.UUID,
    spec: TransformSpec | Any,
) -> tuple[TransformRun, Any]:
    from app.jobs import enqueue

    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None or snapshot.status != "complete":
        raise ValueError("Snapshot nicht gefunden oder nicht abgeschlossen")
    run = TransformRun(
        created_by_oid=str(user["oid"]),
        snapshot_id=snapshot_id,
        spec=spec.model_dump(mode="json"),
        status="previewing",
        candidate_count=len(spec.scope.article_numbers or []),
        error=None,
    )
    db.add(run)
    db.flush()
    job = enqueue(
        db,
        "article_transform_preview",
        {"transform_run_id": str(run.id)},
        user,
    )
    return run, job
