"""German summaries for transform preview and apply chunks."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TransformChunk, TransformRow, TransformRun
from app.transform.schemas import TransformSpec

_OUTCOME_LABELS = {
    "UPDATED": "Aktualisiert",
    "UNCHANGED": "Unverändert",
    "CONFLICT": "Konflikt",
    "REJECTED": "Abgelehnt",
    "GONE": "Nicht mehr vorhanden",
    "REFUSED": "Verweigert",
    "UNAVAILABLE": "Nicht erreichbar",
    "UNKNOWN": "Ausgang unbekannt",
}


def preview_summary(run: TransformRun, *, changed_rows: int | None = None) -> str:
    """Grouped preview text including word-position review lines."""
    changed = changed_rows
    if changed is None:
        changed = sum(1 for row in (run.rows or []) if row.row_status == "CHANGED")
    lines = [f"{changed} Zeilen würden geändert."]
    positions = run.word_positions or {}
    standalone = int(positions.get("standalone") or 0)
    embedded = int(positions.get("embedded") or 0)
    if standalone or embedded:
        lines.append(f"{standalone} Änderungen an eigenständigen Vorkommen")
        lines.append(f"{embedded} Änderungen innerhalb eines zusammengesetzten Wortes")
    if run.spec:
        from app.group_assign import is_group_assign_spec

        if not is_group_assign_spec(run.spec):
            spec = TransformSpec.model_validate(run.spec)
            lines.extend(spec.idempotency_warnings)
    return "\n".join(lines)


def _detail_key(detail: Any) -> str:
    if detail is None:
        return "(kein Detail)"
    if isinstance(detail, str):
        return detail
    try:
        return json.dumps(detail, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(detail)


def format_chunk_result(rows: list[TransformRow]) -> str:
    counts: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    conflicts: list[str] = []
    unknowns: list[str] = []
    unattempted = 0
    for row in rows:
        if not row.apply_outcome:
            unattempted += 1
            continue
        counts[row.apply_outcome] += 1
        if row.apply_outcome == "REJECTED":
            rejected[_detail_key(row.apply_detail)] += 1
        if row.apply_outcome == "CONFLICT":
            conflicts.append(row.article_number)
        if row.apply_outcome == "UNKNOWN":
            unknowns.append(row.article_number)

    lines: list[str] = []
    for key, label in _OUTCOME_LABELS.items():
        n = counts.get(key, 0)
        if key in {"UPDATED", "UNCHANGED"}:
            lines.append(f"{label}: {n}")
            continue
        if n == 0:
            continue
        if key == "CONFLICT":
            numbers = ", ".join(sorted(set(conflicts)))
            lines.append(f"{label}: {n} ({numbers})")
        elif key == "UNKNOWN":
            numbers = ", ".join(sorted(set(unknowns)))
            lines.append(f"{label}: {n} ({numbers})")
            lines.append(
                "Diese Zeilen nicht erneut anwenden — das Schreiben in weclapp "
                "ist möglicherweise bereits erfolgt."
            )
        elif key != "REJECTED":
            lines.append(f"{label}: {n}")
    if rejected:
        lines.append("Abgelehnt, nach Meldung:")
        for message, n in rejected.most_common():
            lines.append(f"  {message}: {n}")
    if unattempted:
        lines.append(f"Nicht ausgeführt: {unattempted}")
    return "\n".join(lines)


def chunk_result_summary(db: Session, chunk: TransformChunk) -> str:
    ids = [UUID(str(item)) for item in (chunk.row_ids or [])]
    if not ids:
        return format_chunk_result([])
    rows = list(db.scalars(select(TransformRow).where(TransformRow.id.in_(ids))))
    by_id = {row.id: row for row in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    return format_chunk_result(ordered)
