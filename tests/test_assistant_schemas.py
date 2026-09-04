"""Pydantic validation for assistant tool arguments."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.assistant.schemas import (
    ArtikelSuchenArgs,
    FilterCondition,
    Operator,
    QueryFilter,
    SortSpec,
)
from app.assistant.tools import MAX_ROWS_TO_MODEL


def test_unknown_column_lists_valid_names():
    with pytest.raises(ValidationError, match="Unbekannte Spalte «nicht_da»") as exc:
        FilterCondition(column="nicht_da", operator=Operator.eq, value="x")
    message = str(exc.value)
    assert "article_number" in message
    assert "Nettogewicht kg" in message


def test_numeric_gt_accepted_on_dimension_columns():
    for column in ("Länge in cm", "Breite in mm", "Höhe in mm"):
        condition = FilterCondition(column=column, operator=Operator.gt, value="10")
        assert condition.column == column
        assert condition.operator == Operator.gt


def test_numeric_operator_on_vpe_rejected():
    with pytest.raises(ValidationError, match="VPE 1"):
        FilterCondition(column="VPE 1", operator=Operator.gte, value="2")


def test_alias_resolves_to_canonical_column():
    condition = FilterCondition(
        column="Prosema Artikelnummer", operator=Operator.eq, value="010.020.0010"
    )
    assert condition.column == "article_number"


def test_in_list_requires_list_and_max_50():
    with pytest.raises(ValidationError, match="Liste"):
        FilterCondition(column="Einheit", operator=Operator.in_list, value="Stk.")
    too_many = [str(i) for i in range(51)]
    with pytest.raises(ValidationError, match="höchstens 50"):
        FilterCondition(column="Einheit", operator=Operator.in_list, value=too_many)


def test_is_null_requires_none_value():
    with pytest.raises(ValidationError, match="keinen Wert"):
        FilterCondition(column="Farbe", operator=Operator.is_null, value="x")
    condition = FilterCondition(column="Farbe", operator=Operator.is_null, value=None)
    assert condition.value is None


def test_limit_above_max_is_clamped():
    args = ArtikelSuchenArgs(limit=500)
    assert args.limit == MAX_ROWS_TO_MODEL


def test_sort_rejects_unknown_and_unsortable():
    with pytest.raises(ValidationError, match="Unbekannte Spalte"):
        SortSpec(column="nope", direction="asc")
    spec = SortSpec(column="Nettogewicht kg", direction="DESC")
    assert spec.direction == "desc"


def test_query_filter_and_only():
    filt = QueryFilter(
        conditions=[
            FilterCondition(column="Einheit", operator=Operator.eq, value="Stk."),
            FilterCondition(column="active", operator=Operator.eq, value="Ja"),
        ]
    )
    assert len(filt.conditions) == 2


def test_volltext_eq_rejected_names_contains():
    with pytest.raises(ValidationError, match="contains") as exc:
        FilterCondition(column="volltext", operator=Operator.eq, value="Messing")
    message = str(exc.value)
    assert "Volltext" in message
    assert "contains" in message
    assert "nicht zulässig" in message


def test_query_filter_requires_conditions_list():
    with pytest.raises(ValidationError):
        QueryFilter.model_validate({})
    with pytest.raises(ValidationError):
        QueryFilter.model_validate({"conditions": None})
    assert QueryFilter.model_validate({"conditions": []}).conditions == []


def test_transform_vorschlagen_schema_requires_conditions():
    from app.assistant.schemas import TransformVorschlagenArgs

    schema = TransformVorschlagenArgs.model_json_schema()
    assert "filters" in schema["required"]
    query = schema["$defs"]["QueryFilter"]
    assert "conditions" in query["required"]
    assert query["properties"]["conditions"]["type"] == "array"


def test_gruppen_zuordnen_schema_requires_ziel():
    from app.assistant.schemas import GruppenZuordnenArgs

    schema = GruppenZuordnenArgs.model_json_schema()
    assert "ziel_gruppe" in schema["required"]
    assert "filters" in schema["required"]
