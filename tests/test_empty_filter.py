"""Empty-filter diagnosis: per-condition counts and similar eq values."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.assistant.catalog import reset_pinned_snapshot, set_pinned_snapshot
from app.assistant.empty_filter import (
    empty_result_can_be_explained,
    explain_empty_filter,
    extract_explainable_filter,
)
from app.assistant.schemas import FilterCondition, Operator, QueryFilter
from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow, AssistantQuery

TENANT = "empty-filter-tenant"

HEADER = [
    {"key": key, "title": key, "width": 120}
    for key in (
        "Prosema Artikelnummer",
        "PROSEMA Kurztext",
        "Grundmaterial",
        "Aktiv",
    )
]


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


def _snapshot(db_session) -> ArticleSnapshot:
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
        row_count=3,
        columns=HEADER,
        created_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()
    rows = [
        {
            "Prosema Artikelnummer": "020.020.0010",
            "PROSEMA Kurztext": "Winkelprofil Edelstahl natur hochglanzpoliert",
            "Grundmaterial": "Edelstahl V2A",
            "Aktiv": "Ja",
        },
        {
            "Prosema Artikelnummer": "020.020.0020",
            "PROSEMA Kurztext": "Winkelprofil Messing natur hochglanzpoliert",
            "Grundmaterial": "Messing",
            "Aktiv": "Ja",
        },
        {
            "Prosema Artikelnummer": "020.020.0030",
            "PROSEMA Kurztext": "Winkelprofil Aluminium roh",
            "Grundmaterial": "Aluminium",
            "Aktiv": "Ja",
        },
    ]
    for position, data in enumerate(rows):
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snap.id,
                position=position,
                data=data,
                article_number=data["Prosema Artikelnummer"],
                article_name=data["PROSEMA Kurztext"],
                active=True,
                weclapp_id=f"id-{position}",
            )
        )
    db_session.flush()
    return snap


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_explain_eq_miss_names_similar_grundmaterial(db_session):
    snap = _snapshot(db_session)
    token = set_pinned_snapshot(snap)
    try:
        text = explain_empty_filter(
            db_session,
            snap,
            QueryFilter(
                conditions=[
                    FilterCondition(
                        column="Grundmaterial", operator=Operator.eq, value="Edelstahl"
                    ),
                    FilterCondition(
                        column="volltext",
                        operator=Operator.contains,
                        value="natur hochglanzpoliert",
                    ),
                ]
            ),
        )
    finally:
        reset_pinned_snapshot(token)
    assert "Zusammen ergeben sie 0 Treffer." in text
    assert "«Grundmaterial» gleich «Edelstahl»: 0 Artikel." in text
    assert "«Edelstahl V2A»" in text
    assert "contains" in text
    assert "natur hochglanzpoliert" in text
    assert "2 Artikel" in text


def test_extract_filter_from_applied_filter():
    query = AssistantQuery(
        user_oid="oid",
        user_name="Tester",
        question_de="Ändern",
        outcome="no_result",
        applied_article_numbers=[],
        applied_filter={
            "conditions": [
                {"column": "Grundmaterial", "operator": "eq", "value": "Edelstahl"}
            ]
        },
    )
    parsed = extract_explainable_filter(query)
    assert parsed is not None
    assert parsed.conditions[0].column == "Grundmaterial"
    assert empty_result_can_be_explained(query) is True


def test_no_button_when_hits_exist():
    query = AssistantQuery(
        user_oid="oid",
        user_name="Tester",
        question_de="Suche",
        outcome="answered",
        total_count=2,
        applied_article_numbers=["020.020.0010", "020.020.0020"],
        applied_filter={
            "conditions": [
                {"column": "volltext", "operator": "contains", "value": "Winkel"}
            ]
        },
    )
    assert empty_result_can_be_explained(query) is False
