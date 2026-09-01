"""Catalogue expressions, aliases, and emptiness encoding."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.assistant.catalog import (
    COLUMNS,
    COMMA_NUMBER_PATTERN,
    VOLLTEXT_COLUMNS,
    column_expression,
    get_column,
    is_empty_expression,
    numeric_expression,
    render_for_prompt,
    resolve_key,
    select_values,
    verify_against_snapshot,
)
from app.assistant.schemas import Operator
from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow

TENANT = "assistant-catalog-tenant"


@pytest.fixture
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


def _snapshot(db_session, *, columns: list[dict], rows: list[dict]) -> ArticleSnapshot:
    snapshot = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
        row_count=len(rows),
        columns=columns,
        created_at=datetime.now(UTC),
    )
    db_session.add(snapshot)
    db_session.flush()
    for position, data in enumerate(rows):
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snapshot.id,
                position=position,
                data=data,
                article_number=str(data.get("Prosema Artikelnummer") or ""),
                article_name=str(data.get("PROSEMA Kurztext") or ""),
                active=data.get("Aktiv") == "Ja",
                weclapp_id=str(data.get("weclapp Artikel-ID") or ""),
            )
        )
    db_session.flush()
    return snapshot


HEADER = [
    {"key": "Prosema Artikelnummer", "title": "Prosema Artikelnummer", "width": 160},
    {"key": "PROSEMA Kurztext", "title": "PROSEMA Kurztext", "width": 220},
    {"key": "Nettogewicht kg", "title": "Nettogewicht kg", "width": 130},
    {"key": "Einkaufspreis EUR netto", "title": "Einkaufspreis EUR netto", "width": 150},
    {"key": "Einheit", "title": "Einheit", "width": 90},
    {"key": "Gewichtseinheit", "title": "Gewichtseinheit", "width": 130},
    {"key": "Steuersatz", "title": "Steuersatz", "width": 120},
]


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_resolve_key_prefers_header_alias(db_session):
    _snapshot(
        db_session,
        columns=HEADER,
        rows=[{"Prosema Artikelnummer": "010.020.0010", "PROSEMA Kurztext": "A"}],
    )
    assert resolve_key(db_session, get_column("article_number")) == "Prosema Artikelnummer"
    assert resolve_key(db_session, get_column("article_name")) == "PROSEMA Kurztext"


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_resolve_key_unavailable_when_alias_missing(db_session):
    _snapshot(
        db_session,
        columns=[{"key": "Einheit", "title": "Einheit", "width": 90}],
        rows=[{"Einheit": "Stk."}],
    )
    col = get_column("Nettogewicht kg")
    assert resolve_key(db_session, col) is None
    with pytest.raises(ValueError, match="nicht vorhanden"):
        column_expression(db_session, col)


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_jsonb_key_bound_as_parameter(db_session):
    _snapshot(db_session, columns=HEADER, rows=[{"Einheit": "Stk."}])
    expr = column_expression(db_session, get_column("Einheit"))
    compiled = expr.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    params = list(compiled.params.values()) if compiled.params else []
    assert "Einheit" in params
    assert "->>'Einheit'" not in sql
    assert "-> 'Einheit'" not in sql


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_numeric_expression_uses_case_and_comma_pattern(db_session):
    _snapshot(db_session, columns=HEADER, rows=[{"Nettogewicht kg": "1,5"}])
    expr = numeric_expression(db_session, get_column("Nettogewicht kg"))
    sql = str(expr.compile(dialect=postgresql.dialect()))
    assert "CASE" in sql.upper() or "case" in sql.lower()
    assert COMMA_NUMBER_PATTERN in sql or "replace" in sql.lower()


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_empty_encoding_absent_vs_empty_string(db_session):
    _snapshot(
        db_session,
        columns=HEADER,
        rows=[
            {"Nettogewicht kg": "", "Einheit": "Stk."},
            {
                "Nettogewicht kg": "1,0",
                "Einkaufspreis EUR netto": "2.00",
                "Einheit": "Stk.",
            },
        ],
    )
    weight = get_column("Nettogewicht kg")
    price = get_column("Einkaufspreis EUR netto")
    assert weight.empty_encoding == "empty_string"
    assert price.empty_encoding == "absent"
    snap = db_session.scalars(
        select(ArticleSnapshot).where(ArticleSnapshot.weclapp_tenant == TENANT)
    ).first()
    empty_weights = list(
        db_session.scalars(
            select(ArticleSnapshotRow).where(
                ArticleSnapshotRow.snapshot_id == snap.id,
                is_empty_expression(db_session, weight),
            )
        )
    )
    empty_prices = list(
        db_session.scalars(
            select(ArticleSnapshotRow).where(
                ArticleSnapshotRow.snapshot_id == snap.id,
                is_empty_expression(db_session, price),
            )
        )
    )
    assert len(empty_weights) == 1
    assert len(empty_prices) == 1


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_gewicht_select_values_collapse(db_session):
    _snapshot(
        db_session,
        columns=HEADER,
        rows=[
            {"Gewichtseinheit": "KILOGRAM"},
            {"Gewichtseinheit": "kg"},
            {"Gewichtseinheit": "KILOGRAM"},
        ],
    )
    assert select_values(db_session, get_column("Gewichtseinheit")) == ("kg",)


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_render_for_prompt_keeps_comma_in_select_value(db_session):
    _snapshot(
        db_session,
        columns=HEADER + [{"key": "Verkaufseinheit", "title": "Verkaufseinheit", "width": 90}],
        rows=[
            {"Verkaufseinheit": "Beutel"},
            {"Verkaufseinheit": "CHF, lfm"},
            {"Verkaufseinheit": "Stück"},
        ],
    )
    prompt = render_for_prompt(db_session)
    assert "«CHF, lfm»" in prompt
    assert "Werte: «Beutel» | «CHF, lfm» | «Stück»" in prompt
    assert "«CHF» | «lfm»" not in prompt


@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_verify_and_prompt(db_session):
    snap = _snapshot(
        db_session,
        columns=HEADER,
        rows=[{"Einheit": "Stk.", "Nettogewicht kg": "1"}],
    )
    warnings = verify_against_snapshot(db_session, snap.id)
    assert any("Steuersatz" in w for w in warnings)
    assert any("Hauptgruppe" in w for w in warnings)
    prompt = render_for_prompt(db_session)
    assert "Nettogewicht kg | number" in prompt
    assert "Länge in cm | text" in prompt
    assert "34 Werte" not in prompt
    assert "weclapp_id | text" in prompt
    assert "hauptgruppe_code" not in prompt
    names = {col.name for col in COLUMNS}
    assert "weclapp_id" in names
    assert "Steuersatz" not in names
    assert "Im Verkauf" not in names
    assert "Bodenleger" not in names
    assert "volltext" in names
    assert not any("Volltext" in w for w in warnings)
    removed = {
        "weclapp Erstellt am",
        "weclapp Geändert am",
        "weclapp Kategorie-ID",
        "weclapp Einheit-ID",
        "weclapp Bezugsquelle-ID",
        "weclapp Breite (m)",
        "weclapp Version",
        "Produkt-ID (Prosema)",
        "Varianten-ID (Prosema)",
    }
    assert names.isdisjoint(removed)
    for name in removed:
        assert name not in prompt
    assert "weclapp Artikel-ID |" not in prompt
    assert "volltext | text | Volltext" in prompt
    assert "contains" in prompt


def test_column_expression_raises_for_virtual():
    col = get_column("volltext")
    assert col is not None
    assert col.storage == "virtual"
    assert col.allowed_operators == (Operator.contains,)
    assert col.sortable is False
    assert set(VOLLTEXT_COLUMNS) <= {c.name for c in COLUMNS}
    with pytest.raises(ValueError, match="virtuelle Spalte «Volltext»"):
        column_expression(None, col)  # session unused; virtual has no expression
