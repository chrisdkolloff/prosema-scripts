"""Compile a QueryFilter into SQLAlchemy clauses for one snapshot.

The snapshot chooses WHICH article rows; it does not supply field values for
writes. Transform preview GETs live weclapp for those.

This module is the shared compiler so transform code does not import
``app.assistant`` tools. ``QueryFilter`` still lives in assistant schemas
(tool argument validation) and is re-exported here.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.models import ArticleSnapshot, ArticleSnapshotRow

_TRUE = frozenset({"ja", "true", "1", "yes"})
_FALSE = frozenset({"nein", "false", "0", "no"})


def _snapshot_scope(snapshot: ArticleSnapshot) -> ColumnElement:
    return ArticleSnapshotRow.snapshot_id == snapshot.id


def _like_pattern(value: str, *, prefix: bool) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
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
    raise ValueError(f"Ungültiger Wahrheitswert «{value}». Erlaubt sind Ja und Nein.")


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
    from app.assistant.catalog import GEWICHT_UNIT_EQUIV

    token = str(value)
    if token in GEWICHT_UNIT_EQUIV:
        return list(GEWICHT_UNIT_EQUIV)
    return [token]


def _clause(
    session: Session,
    snapshot: ArticleSnapshot,
    col: Any,
    condition: Any,
) -> ColumnElement:
    from app.assistant.catalog import (
        column_expression,
        is_empty_expression,
        is_not_empty_expression,
        numeric_expression,
        resolve_key,
        volltext_expression,
    )
    from app.assistant.schemas import Operator

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


def parse_query_filter(data: dict[str, Any]) -> Any:
    """Validate a QueryFilter dict without transform importing ``app.assistant``."""
    from app.assistant.schemas import QueryFilter

    return QueryFilter.model_validate(data)


def filter_clauses(
    session: Session,
    snapshot: ArticleSnapshot,
    filters: Any,
) -> list[ColumnElement]:
    from app.assistant.catalog import get_column

    filters.validate_select_values(session)
    clauses: list[ColumnElement] = [_snapshot_scope(snapshot)]
    for condition in filters.conditions:
        col = get_column(condition.column)
        if col is None:
            raise ValueError(f"Unbekannte Spalte «{condition.column}».")
        clauses.append(_clause(session, snapshot, col, condition))
    return clauses
