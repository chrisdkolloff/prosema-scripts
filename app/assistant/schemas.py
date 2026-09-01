"""Pydantic argument models for assistant tools."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

NUMERIC_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})


class Operator(StrEnum):
    eq = "eq"
    ne = "ne"
    contains = "contains"
    starts_with = "starts_with"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    is_null = "is_null"
    is_not_null = "is_not_null"
    in_list = "in_list"


def _valid_column_names() -> list[str]:
    from app.assistant.catalog import column_names

    return column_names()


def _resolve_column(name: str):
    from app.assistant.catalog import get_column

    return get_column(name)


def _unknown_column_message(name: str) -> str:
    names = ", ".join(_valid_column_names())
    return f"Unbekannte Spalte «{name}». Gültige Spalten: {names}."


class FilterCondition(BaseModel):
    model_config = {"extra": "forbid"}

    column: str
    operator: Operator
    # Concrete JSON types — `Any` emits a typeless schema that Azure strict
    # mode rejects (`schema must have a 'type' key`).
    value: str | list[str] | int | float | None = None

    @model_validator(mode="after")
    def validate_against_catalog(self) -> FilterCondition:
        col = _resolve_column(self.column)
        if col is None:
            raise ValueError(_unknown_column_message(self.column))
        object.__setattr__(self, "column", col.name)

        if self.operator not in col.allowed_operators:
            if col.storage == "virtual":
                raise ValueError(
                    f"Operator «{self.operator}» ist für «{col.label_de}» nicht zulässig. "
                    "Erlaubt ist nur «contains»."
                )
            if self.operator.value in NUMERIC_OPERATORS and col.type != "number":
                from app.assistant.catalog import numeric_rejected_message

                raise ValueError(numeric_rejected_message(col))
            raise ValueError(
                f"Operator «{self.operator}» ist für «{col.label_de}» nicht zulässig."
            )

        if self.operator in {Operator.is_null, Operator.is_not_null}:
            if self.value is not None:
                raise ValueError(
                    f"Operator «{self.operator}» erwartet keinen Wert "
                    f"(value muss leer sein)."
                )
            return self

        if self.operator == Operator.in_list:
            if not isinstance(self.value, list):
                raise ValueError(
                    f"Operator «in_list» für «{col.label_de}» erwartet eine Liste."
                )
            if len(self.value) > 50:
                raise ValueError(
                    f"Operator «in_list» für «{col.label_de}» erlaubt höchstens 50 Werte."
                )
            if any(item is None or item == "" for item in self.value):
                raise ValueError(
                    f"Operator «in_list» für «{col.label_de}» darf keine leeren Werte enthalten."
                )
            return self

        if self.value is None or self.value == "":
            raise ValueError(f"Operator «{self.operator}» für «{col.label_de}» braucht einen Wert.")
        return self


class QueryFilter(BaseModel):
    """AND-only filter. Multi-value questions use ``in_list``, not OR."""

    model_config = {"extra": "forbid"}

    conditions: list[FilterCondition] = Field(default_factory=list)

    def validate_select_values(self, session) -> None:
        """Reject select values that are not in the current snapshot's distinct list."""
        from app.assistant.catalog import (
            GEWICHT_UNIT_EQUIV,
            get_column,
            select_values,
        )

        for condition in self.conditions:
            col = get_column(condition.column)
            if col is None or col.type != "select":
                continue
            if condition.operator not in {Operator.eq, Operator.ne, Operator.in_list}:
                continue
            raw_values = (
                condition.value if condition.operator == Operator.in_list else [condition.value]
            )
            offered = set(select_values(session, col))
            if col.name == "Gewichtseinheit":
                offered |= set(GEWICHT_UNIT_EQUIV)
            invalid = [str(v) for v in raw_values if str(v) not in offered]
            if not invalid:
                continue
            listing = ", ".join(sorted(offered)) or "(keine)"
            raise ValueError(
                f"Ungültiger Wert für «{col.label_de}»: {', '.join(invalid)}. "
                f"Erlaubte Werte: {listing}."
            )


class SortSpec(BaseModel):
    model_config = {"extra": "forbid"}

    column: str
    direction: str = "asc"

    @model_validator(mode="after")
    def validate_sort(self) -> SortSpec:
        direction = self.direction.strip().casefold()
        if direction not in {"asc", "desc"}:
            raise ValueError("Sortierrichtung muss «asc» oder «desc» sein.")
        object.__setattr__(self, "direction", direction)
        col = _resolve_column(self.column)
        if col is None:
            raise ValueError(_unknown_column_message(self.column))
        if not col.sortable:
            raise ValueError(f"«{col.label_de}» kann nicht sortiert werden.")
        object.__setattr__(self, "column", col.name)
        return self


def _clamp_limit(value: object) -> int:
    from app.assistant.tools import MAX_ROWS_TO_MODEL

    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return MAX_ROWS_TO_MODEL
    if parsed < 1:
        return 1
    if parsed > MAX_ROWS_TO_MODEL:
        return MAX_ROWS_TO_MODEL
    return parsed


class ArtikelSuchenArgs(BaseModel):
    model_config = {"extra": "forbid"}

    filters: QueryFilter = Field(default_factory=QueryFilter)
    sort: SortSpec | None = None
    limit: int = 50

    @field_validator("limit", mode="before")
    @classmethod
    def clamp_limit(cls, value: object) -> int:
        return _clamp_limit(value)


class ArtikelZaehlenArgs(BaseModel):
    model_config = {"extra": "forbid"}

    filters: QueryFilter = Field(default_factory=QueryFilter)
    group_by: str | None = None

    @model_validator(mode="after")
    def validate_group_by(self) -> ArtikelZaehlenArgs:
        if self.group_by is None or self.group_by == "":
            object.__setattr__(self, "group_by", None)
            return self
        col = _resolve_column(self.group_by)
        if col is None:
            raise ValueError(_unknown_column_message(self.group_by))
        object.__setattr__(self, "group_by", col.name)
        return self


class ArtikelDetailsArgs(BaseModel):
    model_config = {"extra": "forbid"}

    article_number: str

    @field_validator("article_number")
    @classmethod
    def require_number(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Artikelnummer darf nicht leer sein.")
        return cleaned


class GruppenAuflistenArgs(BaseModel):
    model_config = {"extra": "forbid"}


class EinheitenAuflistenArgs(BaseModel):
    model_config = {"extra": "forbid"}


class DatenstandArgs(BaseModel):
    model_config = {"extra": "forbid"}
