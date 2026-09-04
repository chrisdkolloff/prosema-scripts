"""Read-only query tools over a tenant article snapshot.

By default this is the latest complete snapshot. During ``ask()`` the viewed
snapshot is pinned so older Artikelübersichten query their own rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.assistant.catalog import (
    CONFORMING_NUMBER_PATTERN,
    column_expression,
    get_column,
    hauptgruppe_code_expression,
    is_not_empty_expression,
    numeric_expression,
    resolve_key,
    snapshot_for_query,
    untergruppe_code_expression,
)

from app.assistant.schemas import (
    ArtikelDetailsArgs,
    ArtikelSuchenArgs,
    ArtikelZaehlenArgs,
    DatenstandArgs,
    EinheitenAuflistenArgs,
    GruppenAuflistenArgs,
    SortSpec,
)
from app.config import settings
from app.filter_clauses import filter_clauses as _filter_clauses
from app.models import ArticleSnapshot, ArticleSnapshotRow, Hauptgruppe, Job, Untergruppe
from app.snapshots import format_snapshot_timestamp

MAX_ROWS_TO_MODEL = 50
MAX_ROWS_SCANNED = 5000


@dataclass
class ToolResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    truncated: bool = False
    datenstand: datetime | None = None
    datenstand_hinweis_de: str = ""
    hinweis_de: str = ""


def resolve_current_snapshot(session: Session) -> ArticleSnapshot | None:
    """Complete snapshot for this query: pinned if set, else the latest for the tenant.

    Do not use ``latest_completed_snapshot`` from ``app.numbering_high_water``:
    that helper does not filter by tenant and exists for numbering, not this query layer.
    """
    return snapshot_for_query(session, settings.weclapp_tenant)


def _datenstand_hinweis(snapshot: ArticleSnapshot) -> str:
    stamp = format_snapshot_timestamp(snapshot.created_at)
    return (
        f"Datenstand: Beginn des Abzugs vom {stamp}. "
        "Der Zeitpunkt ist der Start der Abfrage, nicht deren Abschluss."
    )


def _empty_result(*, hinweis: str, snapshot: ArticleSnapshot | None = None) -> ToolResult:
    if snapshot is None:
        return ToolResult(hinweis_de=hinweis, datenstand_hinweis_de=hinweis)
    return ToolResult(
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
        hinweis_de=hinweis,
    )


def _order_by(session: Session, spec: SortSpec | None) -> ColumnElement:
    if spec is None:
        return ArticleSnapshotRow.article_number.asc()
    col = get_column(spec.column)
    if col is None:
        raise ValueError(f"Unbekannte Spalte «{spec.column}».")
    expr = (
        numeric_expression(session, col)
        if col.type == "number"
        else column_expression(session, col)
    )
    ordered = expr.desc() if spec.direction == "desc" else expr.asc()
    if col.type == "number":
        return ordered.nulls_last()
    return ordered


def _row_payload(session: Session, row: ArticleSnapshotRow) -> dict[str, Any]:
    data = row.data if isinstance(row.data, dict) else {}
    payload: dict[str, Any] = {
        "article_number": row.article_number,
        "article_name": row.article_name,
        "active": row.active,
        "weclapp_id": row.weclapp_id,
        "weclapp_version": row.weclapp_version,
    }
    for col in (
        get_column("Hauptgruppe"),
        get_column("Untergruppe"),
        get_column("Einheit"),
        get_column("Nettogewicht kg"),
        get_column("Nettoverkaufspreis CHF"),
        get_column("Einkaufspreis EUR netto"),
        get_column("Kategorie"),
        get_column("Lieferantenartikelnummer"),
    ):
        if col is None or col.storage != "jsonb":
            continue
        key = resolve_key(session, col)
        if key is None:
            continue
        if key in data:
            payload[col.name] = data[key]
    return payload


def _detail_payload(session: Session, row: ArticleSnapshotRow) -> dict[str, Any]:
    data = dict(row.data) if isinstance(row.data, dict) else {}
    payload = _row_payload(session, row)
    payload["data"] = data
    return payload


def artikel_suchen(session: Session, args: ArtikelSuchenArgs) -> ToolResult:
    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return _empty_result(hinweis="Kein abgeschlossener Artikel-Snapshot vorhanden.")
    clauses = _filter_clauses(session, snapshot, args.filters)
    where = and_(*clauses)
    total = int(session.scalar(select(func.count()).where(where)) or 0)
    stmt = (
        select(ArticleSnapshotRow)
        .where(where)
        .order_by(_order_by(session, args.sort), ArticleSnapshotRow.position)
        .limit(min(args.limit, MAX_ROWS_TO_MODEL, MAX_ROWS_SCANNED))
    )
    rows = [_row_payload(session, row) for row in session.scalars(stmt)]
    truncated = total > len(rows)
    hinweis = ""
    if truncated:
        hinweis = (
            f"Es gibt {total} Treffer; es werden {len(rows)} Zeilen gezeigt "
            f"(Maximum {MAX_ROWS_TO_MODEL})."
        )
    return ToolResult(
        rows=rows,
        total_count=total,
        truncated=truncated,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
        hinweis_de=hinweis,
    )


def artikel_zaehlen(session: Session, args: ArtikelZaehlenArgs) -> ToolResult:
    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return _empty_result(hinweis="Kein abgeschlossener Artikel-Snapshot vorhanden.")
    clauses = _filter_clauses(session, snapshot, args.filters)
    where = and_(*clauses)
    if not args.group_by:
        total = int(session.scalar(select(func.count()).where(where)) or 0)
        return ToolResult(
            rows=[{"anzahl": total}],
            total_count=total,
            truncated=False,
            datenstand=snapshot.created_at,
            datenstand_hinweis_de=_datenstand_hinweis(snapshot),
        )

    col = get_column(args.group_by)
    if col is None:
        raise ValueError(f"Unbekannte Spalte «{args.group_by}».")
    group_expr = column_expression(session, col)
    grouped = (
        select(group_expr.label("gruppe"), func.count().label("anzahl"))
        .where(where)
        .group_by(group_expr)
        .order_by(func.count().desc(), group_expr)
    )
    all_groups = list(session.execute(grouped).all())
    truncated = len(all_groups) > MAX_ROWS_TO_MODEL
    shown = all_groups[:MAX_ROWS_TO_MODEL]
    hinweis = ""
    if truncated:
        hinweis = (
            f"Es gibt {len(all_groups)} Gruppen; es werden die {MAX_ROWS_TO_MODEL} "
            "grössten gezeigt."
        )
    rows = [{"gruppe": row[0], "anzahl": int(row[1])} for row in shown]
    return ToolResult(
        rows=rows,
        total_count=len(all_groups),
        truncated=truncated,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
        hinweis_de=hinweis,
    )


def artikel_details(session: Session, args: ArtikelDetailsArgs) -> ToolResult:
    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return _empty_result(hinweis="Kein abgeschlossener Artikel-Snapshot vorhanden.")
    row = session.scalars(
        select(ArticleSnapshotRow).where(
            ArticleSnapshotRow.snapshot_id == snapshot.id,
            ArticleSnapshotRow.article_number == args.article_number,
        )
    ).first()
    if row is None:
        return ToolResult(
            rows=[],
            total_count=0,
            truncated=False,
            datenstand=snapshot.created_at,
            datenstand_hinweis_de=_datenstand_hinweis(snapshot),
            hinweis_de=f"Kein Artikel mit Nummer «{args.article_number}» im aktuellen Snapshot.",
        )
    return ToolResult(
        rows=[_detail_payload(session, row)],
        total_count=1,
        truncated=False,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
    )


def gruppen_auflisten(session: Session, args: GruppenAuflistenArgs) -> ToolResult:
    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return _empty_result(hinweis="Kein abgeschlossener Artikel-Snapshot vorhanden.")

    hg_expr = hauptgruppe_code_expression()
    ug_expr = untergruppe_code_expression()
    scoped = ArticleSnapshotRow.snapshot_id == snapshot.id

    hg_counts = {
        str(code): int(count)
        for code, count in session.execute(
            select(hg_expr, func.count())
            .where(scoped, hg_expr.is_not(None))
            .group_by(hg_expr)
        ).all()
    }
    ug_counts = {
        (str(hg), str(ug)): int(count)
        for hg, ug, count in session.execute(
            select(hg_expr, ug_expr, func.count())
            .where(scoped, hg_expr.is_not(None), ug_expr.is_not(None))
            .group_by(hg_expr, ug_expr)
        ).all()
    }
    non_conforming = int(
        session.scalar(
            select(func.count()).where(
                scoped,
                ~ArticleSnapshotRow.article_number.op("~")(CONFORMING_NUMBER_PATTERN),
            )
        )
        or 0
    )

    rows: list[dict[str, Any]] = []
    hauptgruppen = list(
        session.scalars(
            select(Hauptgruppe)
            .where(Hauptgruppe.deleted_at.is_(None))
            .order_by(Hauptgruppe.code)
        )
    )
    untergruppen = list(
        session.scalars(
            select(Untergruppe)
            .where(Untergruppe.deleted_at.is_(None))
            .order_by(Untergruppe.code)
        )
    )
    unter_by_parent: dict[uuid.UUID, list[Untergruppe]] = {}
    for unter in untergruppen:
        unter_by_parent.setdefault(unter.hauptgruppe_id, []).append(unter)

    for haupt in hauptgruppen:
        rows.append(
            {
                "ebene": "hauptgruppe",
                "code": haupt.code,
                "name": haupt.name,
                "anzahl": hg_counts.get(haupt.code, 0),
            }
        )
        for unter in unter_by_parent.get(haupt.id, []):
            rows.append(
                {
                    "ebene": "untergruppe",
                    "code": unter.code,
                    "name": unter.name,
                    "hauptgruppe_code": haupt.code,
                    "anzahl": ug_counts.get((haupt.code, unter.code), 0),
                }
            )

    hinweis = ""
    if non_conforming:
        hinweis = (
            f"{non_conforming} Artikel haben keine konforme Nummer und sind "
            "in den Gruppencounts nicht enthalten."
        )
    return ToolResult(
        rows=rows,
        total_count=len(rows),
        truncated=False,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
        hinweis_de=hinweis,
    )


def einheiten_auflisten(session: Session, args: EinheitenAuflistenArgs) -> ToolResult:
    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return _empty_result(hinweis="Kein abgeschlossener Artikel-Snapshot vorhanden.")
    col = get_column("Einheit")
    if col is None:
        return _empty_result(hinweis="Spalte Einheit fehlt im Katalog.", snapshot=snapshot)
    # TODO: there is no units table in PostgreSQL; DISTINCT over the snapshot
    # Einheit key is the only source of unit names.
    expr = column_expression(session, col)
    stmt = (
        select(expr, func.count())
        .where(
            ArticleSnapshotRow.snapshot_id == snapshot.id,
            is_not_empty_expression(session, col),
        )
        .group_by(expr)
        .order_by(func.count().desc(), expr)
    )
    rows = [{"name": name, "anzahl": int(count)} for name, count in session.execute(stmt).all()]
    return ToolResult(
        rows=rows,
        total_count=len(rows),
        truncated=False,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
    )


def datenstand(session: Session, args: DatenstandArgs) -> ToolResult:
    snapshot = resolve_current_snapshot(session)
    job = session.scalars(
        select(Job)
        .where(Job.job_type == "weclapp_article_snapshot")
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()
    job_payload = None
    if job is not None:
        job_payload = {
            "id": str(job.id),
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error": job.error,
        }
    if snapshot is None:
        return ToolResult(
            rows=[
                {
                    "snapshot_id": None,
                    "created_at": None,
                    "row_count": None,
                    "non_conforming_number_count": None,
                    "job": job_payload,
                }
            ],
            hinweis_de="Kein abgeschlossener Artikel-Snapshot vorhanden.",
            datenstand_hinweis_de="Kein abgeschlossener Artikel-Snapshot vorhanden.",
        )
    return ToolResult(
        rows=[
            {
                "snapshot_id": str(snapshot.id),
                "created_at": snapshot.created_at.isoformat(),
                "row_count": snapshot.row_count,
                "non_conforming_number_count": snapshot.non_conforming_number_count,
                "job": job_payload,
            }
        ],
        total_count=snapshot.row_count or 0,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
    )


_PROPOSE_ONLY_FORBIDDEN = frozenset(
    {
        "start_transform_preview",
        "start_transform_apply",
        "update_article",
        "update_article_category",
        "approve_chunk",
        "reconcile_unknown_row",
    }
)


def _transform_spec_error_de(exc: BaseException) -> str:
    from app.transform.schemas import TransformSpecError

    if isinstance(exc, TransformSpecError):
        return exc.message_de
    if isinstance(exc, ValidationError):
        for err in exc.errors():
            ctx = err.get("ctx") or {}
            inner = ctx.get("error")
            if isinstance(inner, TransformSpecError):
                return inner.message_de
            msg = str(err.get("msg") or "").removeprefix("Value error, ").strip()
            if msg:
                return msg
    return str(exc) or "Die Vorgabe ist ungültig."


def snapshot_key_for_transform_field(name: str) -> str:
    """Map an assistant column name or alias to a write-catalogue snapshot_key.

    Does not add a third vocabulary: ``get_column`` then ``write_field`` on the
    column's label and aliases. Unknown names are returned unchanged so
    TransformSpec can refuse them.
    """
    from core.article_write_fields import write_field

    cleaned = (name or "").strip()
    if not cleaned:
        return cleaned
    try:
        return write_field(cleaned).snapshot_key
    except KeyError:
        pass
    col = get_column(cleaned)
    if col is None:
        return cleaned
    for candidate in (col.label_de, *col.aliases, col.name):
        if not candidate:
            continue
        try:
            return write_field(candidate).snapshot_key
        except KeyError:
            continue
    return cleaned


def _snapshot_field_text(session: Session, row: ArticleSnapshotRow, snapshot_key: str) -> str:
    col = get_column(snapshot_key)
    if col is not None and col.storage == "column" and col.column_attr:
        return str(getattr(row, col.column_attr, None) or "")
    data = row.data if isinstance(row.data, dict) else {}
    if col is not None:
        header_key = resolve_key(session, col)
        if header_key and data.get(header_key) is not None:
            return str(data[header_key])
        for key in col.json_keys:
            if data.get(key) is not None:
                return str(data[key])
    return str(data.get(snapshot_key) or "")


def transform_vorschlagen(session: Session, args: Any) -> ToolResult:
    """Return a validated TransformSpec. Never preview, enqueue, or write."""
    leaked = _PROPOSE_ONLY_FORBIDDEN & set(globals())
    assert not leaked, (
        "transform_vorschlagen must not bind preview, apply, or write helpers: "
        f"{sorted(leaked)}"
    )

    from app.assistant.schemas import TransformVorschlagenArgs
    from app.transform.schemas import (
        TransformSpec,
        TransformSpecError,
        destructive_insertion_refusal,
    )

    if not isinstance(args, TransformVorschlagenArgs):
        args = TransformVorschlagenArgs.model_validate(args)

    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return _empty_result(hinweis="Kein abgeschlossener Artikel-Snapshot vorhanden.")

    try:
        operations = []
        for operation in args.operations:
            item: dict[str, str] = {"op": operation.op, "search": operation.search}
            if operation.op in {"replace_word", "replace_literal"}:
                item["replace"] = operation.replace or ""
            operations.append(item)
        spec = TransformSpec.model_validate(
            {
                "scope": {"query_filter": args.filters.model_dump(mode="json")},
                "fields": [
                    snapshot_key_for_transform_field(key) for key in args.fields
                ],
                "operations": operations,
            }
        )
        clauses = _filter_clauses(session, snapshot, args.filters)
        total = int(session.scalar(select(func.count()).where(and_(*clauses))) or 0)
        scoped_rows = list(session.scalars(select(ArticleSnapshotRow).where(and_(*clauses))))
        field_values = [
            _snapshot_field_text(session, row, key)
            for row in scoped_rows
            for key in spec.fields
        ]
        for operation in spec.operations:
            refused = destructive_insertion_refusal(operation, field_values)
            if refused:
                return ToolResult(
                    rows=[],
                    total_count=total,
                    datenstand=snapshot.created_at,
                    datenstand_hinweis_de=_datenstand_hinweis(snapshot),
                    hinweis_de=refused,
                )
    except (TransformSpecError, ValidationError, ValueError) as exc:
        message = _transform_spec_error_de(exc)
        return ToolResult(
            rows=[],
            total_count=0,
            datenstand=snapshot.created_at,
            datenstand_hinweis_de=_datenstand_hinweis(snapshot),
            hinweis_de=message,
        )

    warnings = list(spec.idempotency_warnings)
    return ToolResult(
        rows=[
            {
                "spec": spec.model_dump(mode="json"),
                "warnings": warnings,
            }
        ],
        total_count=total,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
        hinweis_de="\n".join(warnings),
    )


def gruppen_zuordnen(session: Session, args: Any) -> ToolResult:
    """Return a validated GroupAssignSpec. Never preview, enqueue, or write."""
    leaked = _PROPOSE_ONLY_FORBIDDEN & set(globals())
    assert not leaked, (
        "gruppen_zuordnen must not bind preview, apply, or write helpers: "
        f"{sorted(leaked)}"
    )

    from app.assistant.schemas import GruppenZuordnenArgs
    from app.group_assign import (
        MSG_EMPTY_SCOPE,
        MSG_NUMBERS_UNCHANGED,
        build_group_assign_spec,
    )

    if not isinstance(args, GruppenZuordnenArgs):
        args = GruppenZuordnenArgs.model_validate(args)

    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return _empty_result(hinweis="Kein abgeschlossener Artikel-Snapshot vorhanden.")

    if not args.filters.conditions:
        return ToolResult(
            rows=[],
            total_count=0,
            datenstand=snapshot.created_at,
            datenstand_hinweis_de=_datenstand_hinweis(snapshot),
            hinweis_de=MSG_EMPTY_SCOPE,
        )

    try:
        spec = build_group_assign_spec(
            session,
            filters=args.filters.model_dump(mode="json"),
            ziel=args.ziel_gruppe,
        )
        clauses = _filter_clauses(session, snapshot, args.filters)
        total = int(session.scalar(select(func.count()).where(and_(*clauses))) or 0)
    except (ValidationError, ValueError) as exc:
        message = str(exc)
        return ToolResult(
            rows=[],
            total_count=0,
            datenstand=snapshot.created_at,
            datenstand_hinweis_de=_datenstand_hinweis(snapshot),
            hinweis_de=message,
        )

    return ToolResult(
        rows=[{"spec": spec.model_dump(mode="json")}],
        total_count=total,
        datenstand=snapshot.created_at,
        datenstand_hinweis_de=_datenstand_hinweis(snapshot),
        hinweis_de=MSG_NUMBERS_UNCHANGED,
    )
