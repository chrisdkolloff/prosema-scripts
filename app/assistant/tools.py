"""Read-only query tools over the current article snapshot."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.assistant.catalog import (
    CONFORMING_NUMBER_PATTERN,
    GEWICHT_UNIT_EQUIV,
    QueryableColumn,
    column_expression,
    get_column,
    hauptgruppe_code_expression,
    is_empty_expression,
    is_not_empty_expression,
    numeric_expression,
    resolve_key,
    untergruppe_code_expression,
    volltext_expression,
)
from app.assistant.schemas import (
    ArtikelDetailsArgs,
    ArtikelSuchenArgs,
    ArtikelZaehlenArgs,
    DatenstandArgs,
    EinheitenAuflistenArgs,
    FilterCondition,
    GruppenAuflistenArgs,
    Operator,
    QueryFilter,
    SortSpec,
)
from app.config import settings
from app.models import ArticleSnapshot, ArticleSnapshotRow, Hauptgruppe, Job, Untergruppe
from app.snapshots import format_snapshot_timestamp

MAX_ROWS_TO_MODEL = 50
MAX_ROWS_SCANNED = 5000

_TRUE = frozenset({"ja", "true", "1", "yes"})
_FALSE = frozenset({"nein", "false", "0", "no"})


@dataclass
class ToolResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    truncated: bool = False
    datenstand: datetime | None = None
    datenstand_hinweis_de: str = ""
    hinweis_de: str = ""


def resolve_current_snapshot(session: Session) -> ArticleSnapshot | None:
    """Latest complete snapshot for this tenant.

    Do not use ``latest_completed_snapshot`` from ``app.numbering_high_water``:
    that helper does not filter by tenant and exists for numbering, not this query layer.
    """
    tenant = settings.weclapp_tenant.strip()
    return session.scalars(
        select(ArticleSnapshot)
        .where(
            ArticleSnapshot.status == "complete",
            ArticleSnapshot.weclapp_tenant == tenant,
        )
        .order_by(ArticleSnapshot.created_at.desc())
        .limit(1)
    ).first()


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


def _snapshot_scope(snapshot: ArticleSnapshot) -> ColumnElement:
    return ArticleSnapshotRow.snapshot_id == snapshot.id


def _like_pattern(value: str, *, prefix: bool) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    if prefix:
        return f"{escaped}%"
    return f"%{escaped}%"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value).strip().casefold()
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    raise ValueError(
        f"Ungültiger Wahrheitswert «{value}». Erlaubt sind Ja und Nein."
    )


def _coerce_number(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    text = str(value).strip().replace("'", "").replace("\u2019", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Ungültiger Zahlenwert «{value}».") from exc


def _gewicht_values(value: Any) -> list[str]:
    token = str(value)
    if token in GEWICHT_UNIT_EQUIV:
        return list(GEWICHT_UNIT_EQUIV)
    return [token]


def _clause(
    session: Session,
    snapshot: ArticleSnapshot,
    col: QueryableColumn,
    condition: FilterCondition,
) -> ColumnElement:
    if not col.filterable:
        raise ValueError(f"«{col.label_de}» kann nicht gefiltert werden.")
    if col.storage == "virtual":
        if condition.operator != Operator.contains:
            raise ValueError(
                f"Operator «{condition.operator}» ist für «{col.label_de}» nicht zulässig. "
                "Erlaubt ist nur «contains»."
            )
        return volltext_expression(session, str(condition.value))
    if col.storage == "jsonb" and resolve_key(session, col) is None:
        raise ValueError(
            f"Die Spalte «{col.label_de}» ist in diesem Snapshot nicht vorhanden."
        )

    if condition.operator == Operator.is_null:
        return is_empty_expression(session, col)
    if condition.operator == Operator.is_not_null:
        return is_not_empty_expression(session, col)

    if col.type == "number":
        expr = numeric_expression(session, col)
        number = _coerce_number(condition.value)
        ops = {
            Operator.eq: expr == number,
            Operator.ne: expr != number,
            Operator.gt: expr > number,
            Operator.gte: expr >= number,
            Operator.lt: expr < number,
            Operator.lte: expr <= number,
        }
        return ops[condition.operator]

    expr = column_expression(session, col)

    if col.type == "bool":
        flag = _coerce_bool(condition.value)
        if condition.operator == Operator.eq:
            return expr.is_(flag)
        return expr.is_not(flag)

    if col.name == "Gewichtseinheit" and condition.operator in {
        Operator.eq,
        Operator.ne,
        Operator.in_list,
    }:
        raw_items = (
            condition.value if condition.operator == Operator.in_list else [condition.value]
        )
        expanded: list[str] = []
        for item in raw_items:
            expanded.extend(_gewicht_values(item))
        unique = list(dict.fromkeys(expanded))
        if condition.operator == Operator.ne:
            return or_(expr.not_in(unique), is_empty_expression(session, col))
        return expr.in_(unique)

    if condition.operator == Operator.eq:
        return expr == str(condition.value)
    if condition.operator == Operator.ne:
        return or_(expr != str(condition.value), is_empty_expression(session, col))
    if condition.operator == Operator.contains:
        return expr.ilike(_like_pattern(str(condition.value), prefix=False), escape="\\")
    if condition.operator == Operator.starts_with:
        return expr.ilike(_like_pattern(str(condition.value), prefix=True), escape="\\")
    if condition.operator == Operator.in_list:
        return expr.in_([str(item) for item in condition.value])
    raise ValueError(f"Operator «{condition.operator}» wird nicht unterstützt.")


def _filter_clauses(
    session: Session,
    snapshot: ArticleSnapshot,
    filters: QueryFilter,
) -> list[ColumnElement]:
    filters.validate_select_values(session)
    clauses: list[ColumnElement] = [_snapshot_scope(snapshot)]
    for condition in filters.conditions:
        col = get_column(condition.column)
        if col is None:
            raise ValueError(f"Unbekannte Spalte «{condition.column}».")
        clauses.append(_clause(session, snapshot, col, condition))
    return clauses


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
