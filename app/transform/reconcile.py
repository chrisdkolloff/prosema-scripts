"""Resolve UNKNOWN transform rows by live GET. Never writes to weclapp."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article_write import (
    MSG_AUDIT_RECONSTRUCTED,
    ArticleWriteAuditDetail,
    ArticleWriteFieldChange,
    live_field_value,
)
from app.audit import record_audit_log
from app.models import TransformChunk, TransformRow, TransformRun
from app.weclapp import weclapp_client_for
from core.article_write_fields import CustomAttributeResolver, write_field
from scripts.weclapp.client import WeclappClient, WeclappError

MSG_RECONCILE_LANDED = "Schreiben bestätigt. Protokoll nachträglich ergänzt."
MSG_RECONCILE_NOT_LANDED = "Schreiben nicht erfolgt. Zeile ist erneut anwendbar."
MSG_RECONCILE_DIVERGED = "Wert abweichend. Neue Vorschau nötig."
MSG_RECONCILE_SUMMARY = (
    "Abgleich: {landed} Schreiben bestätigt, {not_landed} erneut anwendbar, "
    "{diverged} abweichend (neue Vorschau nötig)."
)

ReconcileKind = Literal["landed", "not_landed", "diverged"]


class GetOnlyWeclappClient:
    """Forwards reads; any write method raises AssertionError."""

    def __init__(self, inner: WeclappClient) -> None:
        self._inner = inner

    def get(self, path: str, *, params=None) -> Any:
        return self._inner.get(path, params=params)

    def get_count(self, entity: str, *, params=None) -> int:
        return self._inner.get_count(entity, params=params)

    def iter_pages(self, entity: str, *, params=None, page_size=None):
        return self._inner.iter_pages(entity, params=params, page_size=page_size)

    def put(self, path: str, *, params=None, json=None) -> Any:
        raise AssertionError("UNKNOWN reconcile must not PUT")

    def post(self, path: str, *, params=None, json=None) -> Any:
        raise AssertionError("UNKNOWN reconcile must not PUT")


@dataclass
class ReconcileRowResult:
    kind: ReconcileKind
    message_de: str
    article_number: str


def _write_guard(client: WeclappClient) -> GetOnlyWeclappClient:
    if isinstance(client, GetOnlyWeclappClient):
        return client
    return GetOnlyWeclappClient(client)


def reconcile_unknown_row(
    db: Session,
    row: TransformRow,
    *,
    oid: str,
    actor_name: str | None = None,
    client: WeclappClient | None = None,
    chunk_id: str | None = None,
) -> ReconcileRowResult:
    """GET live weclapp and update the UNKNOWN row. Asserts no PUT."""
    if row.apply_outcome != "UNKNOWN":
        raise ValueError("Nur Zeilen mit unbekanntem Ausgang können abgeglichen werden")
    wc = _write_guard(client or weclapp_client_for(db, oid))
    resolver = CustomAttributeResolver(wc)
    resolver.load()
    try:
        article = wc.get(f"/article/id/{row.weclapp_id}")
    except WeclappError as exc:
        row.apply_detail = str(exc)
        db.commit()
        raise
    if not isinstance(article, dict):
        raise TypeError("weclapp GET /article did not return an object")
    live = live_field_value(article, row.field, resolver)
    actor = actor_name or oid
    run_id = str(row.run_id)

    if live == row.new_value:
        spec = write_field(row.field)
        version_live = str(article.get("version") or "") or None
        detail = ArticleWriteAuditDetail(
            weclapp_id=row.weclapp_id,
            article_number=row.article_number,
            version_before=row.version_at_preview or "",
            version_after=version_live,
            fields=[
                ArticleWriteFieldChange(
                    snapshot_key=row.field,
                    target=spec.target,
                    location=spec.location.value,
                    attribute_definition_id=None,
                    old=row.old_value,
                    new=row.new_value,
                )
            ],
            transform_run_id=run_id,
            transform_chunk_id=chunk_id,
            reconstructed=True,
            reconstructed_note=MSG_AUDIT_RECONSTRUCTED,
        )
        record_audit_log(
            db,
            actor={"oid": oid, "name": actor},
            entity_type="weclapp_article",
            entity_id=row.weclapp_id,
            action="updated",
            detail=detail.model_dump(mode="json"),
        )
        row.apply_outcome = "UPDATED"
        row.apply_detail = MSG_RECONCILE_LANDED
        db.commit()
        return ReconcileRowResult("landed", MSG_RECONCILE_LANDED, row.article_number)

    if live == row.old_value:
        row.apply_outcome = None
        row.apply_detail = None
        db.commit()
        return ReconcileRowResult("not_landed", MSG_RECONCILE_NOT_LANDED, row.article_number)

    row.apply_outcome = "CONFLICT"
    row.apply_detail = MSG_RECONCILE_DIVERGED
    row.apply_version_seen = str(article.get("version") or "") or row.apply_version_seen
    db.commit()
    return ReconcileRowResult("diverged", MSG_RECONCILE_DIVERGED, row.article_number)


def reconcile_unknown_chunk(
    db: Session,
    chunk: TransformChunk,
    *,
    oid: str,
    actor_name: str | None = None,
    client: WeclappClient | None = None,
) -> dict[str, Any]:
    """Reconcile every UNKNOWN row in the chunk. GET only."""
    wc = _write_guard(client or weclapp_client_for(db, oid))
    run = db.get(TransformRun, chunk.run_id)
    if run is None:
        raise ValueError("Transform-Lauf nicht gefunden")
    ids = [uuid.UUID(str(item)) for item in chunk.row_ids]
    by_id = {
        row.id: row
        for row in db.scalars(select(TransformRow).where(TransformRow.id.in_(ids)))
    }
    ordered = [by_id[i] for i in ids if i in by_id]
    counts = {"landed": 0, "not_landed": 0, "diverged": 0}
    results: list[ReconcileRowResult] = []
    for row in ordered:
        db.refresh(row)
        if row.apply_outcome != "UNKNOWN":
            continue
        result = reconcile_unknown_row(
            db,
            row,
            oid=oid,
            actor_name=actor_name,
            client=wc,
            chunk_id=str(chunk.id),
        )
        counts[result.kind] += 1
        results.append(result)
    summary = MSG_RECONCILE_SUMMARY.format(**counts)
    return {"summary": summary, "counts": counts, "results": results}
