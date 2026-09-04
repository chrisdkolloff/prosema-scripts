"""Explain why a catalogue filter matched no articles."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.assistant.catalog import column_expression, get_column
from app.assistant.schemas import FilterCondition, Operator, QueryFilter
from app.filter_clauses import filter_clauses, parse_query_filter
from app.models import ArticleSnapshot, ArticleSnapshotRow, AssistantQuery
from app.snapshots import format_swiss_number
from app.transform.ui import proposed_spec_from_tool_calls

_OP_DE = {
    Operator.eq: "gleich",
    Operator.ne: "ungleich",
    Operator.contains: "enthält",
    Operator.starts_with: "beginnt mit",
    Operator.gt: "grösser als",
    Operator.gte: "mindestens",
    Operator.lt: "kleiner als",
    Operator.lte: "höchstens",
    Operator.is_null: "ist leer",
    Operator.is_not_null: "ist nicht leer",
    Operator.in_list: "ist eines von",
}

_SIMILAR_LIMIT = 8


def extract_explainable_filter(query: AssistantQuery) -> QueryFilter | None:
    """Return the AND-filter that produced the empty result, if any."""
    candidates: list[Any] = []
    if isinstance(query.applied_filter, dict):
        candidates.append(query.applied_filter)
    spec = proposed_spec_from_tool_calls(query.tool_calls)
    if spec is not None:
        scope = getattr(spec, "scope", None)
        qf = getattr(scope, "query_filter", None) if scope is not None else None
        if qf is not None:
            candidates.append(qf if isinstance(qf, dict) else qf)
    for call in reversed(query.tool_calls or []):
        if not isinstance(call, dict) or call.get("error"):
            continue
        args = call.get("arguments") or {}
        if isinstance(args, dict) and isinstance(args.get("filters"), dict):
            candidates.append(args["filters"])
    for raw in candidates:
        try:
            parsed = (
                raw
                if isinstance(raw, QueryFilter)
                else parse_query_filter(raw if isinstance(raw, dict) else {})
            )
        except (ValueError, TypeError):
            continue
        if parsed.conditions:
            return parsed
    return None


def empty_result_can_be_explained(query: AssistantQuery) -> bool:
    if query.selection_truncated:
        return False
    if extract_explainable_filter(query) is None:
        return False
    numbers = query.applied_article_numbers
    if numbers is not None and len(numbers) == 0:
        return True
    if query.total_count == 0:
        return True
    return query.outcome == "no_result"


def explain_empty_filter(
    session: Session,
    snapshot: ArticleSnapshot,
    filters: QueryFilter,
) -> str:
    """German first-person text: combined count plus each condition alone."""
    combined = _count(session, snapshot, filters)
    lines = [
        "Ich habe die Bedingungen einzeln geprüft, weil sie alle gleichzeitig "
        "erfüllt sein müssen."
    ]
    if combined == 0:
        lines.append("Zusammen ergeben sie 0 Treffer.")
    else:
        lines.append(
            f"Zusammen ergeben sie {format_swiss_number(combined)} Treffer."
        )

    for condition in filters.conditions:
        alone = QueryFilter(conditions=[condition])
        n = _count(session, snapshot, alone)
        lines.append(f"{_phrase(condition)}: {format_swiss_number(n)} Artikel.")
        if condition.operator == Operator.eq and n == 0:
            similar = _similar_values(session, snapshot, condition)
            if similar:
                shown = ", ".join(
                    f"«{value}» ({format_swiss_number(count)})"
                    for value, count in similar
                )
                lines.append(
                    "Gleichheit trifft nur den kompletten gespeicherten Wert, "
                    f"nicht einen Teil. Ähnliche Werte: {shown}. "
                    "Mit «contains» statt «eq» wären diese Artikel dabei."
                )
    return " ".join(lines)


def _count(session: Session, snapshot: ArticleSnapshot, filters: QueryFilter) -> int:
    clauses = filter_clauses(session, snapshot, filters)
    return int(session.scalar(select(func.count()).where(and_(*clauses))) or 0)


def _phrase(condition: FilterCondition) -> str:
    col = get_column(condition.column)
    label = col.label_de if col is not None else condition.column
    op = _OP_DE.get(condition.operator, condition.operator.value)
    if condition.operator in {Operator.is_null, Operator.is_not_null}:
        return f"«{label}» {op}"
    if condition.operator == Operator.in_list:
        items = ", ".join(f"«{item}»" for item in (condition.value or []))
        return f"«{label}» {op} {items}"
    return f"«{label}» {op} «{condition.value}»"


def _similar_values(
    session: Session,
    snapshot: ArticleSnapshot,
    condition: FilterCondition,
) -> list[tuple[str, int]]:
    col = get_column(condition.column)
    if col is None or col.storage == "virtual":
        return []
    token = str(condition.value or "").strip()
    if not token:
        return []
    try:
        expr = column_expression(session, col)
    except ValueError:
        return []
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    rows = session.execute(
        select(expr, func.count())
        .where(
            ArticleSnapshotRow.snapshot_id == snapshot.id,
            expr.ilike(pattern, escape="\\"),
            expr != "",
        )
        .group_by(expr)
        .order_by(func.count().desc(), expr)
        .limit(_SIMILAR_LIMIT)
    ).all()
    out: list[tuple[str, int]] = []
    for value, count in rows:
        if value is None:
            continue
        text = str(value)
        if text == token:
            continue
        out.append((text, int(count)))
    return out
