"""Group reassignment: parse, registry resolve, propose-only tool."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.assistant.schemas import GruppenZuordnenArgs
from app.assistant.tools import gruppen_zuordnen
from app.db import engine
from app.group_assign import (
    MSG_EMPTY_SCOPE,
    MSG_NUMBERS_UNCHANGED,
    build_group_assign_spec,
    parse_ziel_gruppe,
    run_group_assign_preview,
)
from app.models import ArticleSnapshot, ArticleSnapshotRow, Hauptgruppe, TransformRun, Untergruppe


TENANT = "group-assign-tenant"


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


@pytest.fixture
def groups(db_session):
    haupt = Hauptgruppe(code="884", name="ZielHG")
    db_session.add(haupt)
    db_session.flush()
    unter = Untergruppe(hauptgruppe_id=haupt.id, code="131", name="ZielUG")
    db_session.add(unter)
    db_session.flush()
    return haupt, unter


@pytest.fixture
def snapshot(db_session):
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
        row_count=2,
        columns=[],
        created_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()
    for position, number in enumerate(("060.020.0010", "060.020.0020")):
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snap.id,
                position=position,
                data={"Prosema Artikelnummer": number},
                article_number=number,
                article_name=f"Artikel {position}",
                active=True,
                weclapp_id=f"id-{position}",
            )
        )
    db_session.flush()
    return snap


def test_parse_ziel_gruppe():
    assert parse_ziel_gruppe("100.130") == ("100", "130")
    assert parse_ziel_gruppe("100.130.0010") == ("100", "130")
    with pytest.raises(ValueError, match="100.130"):
        parse_ziel_gruppe("100")
    with pytest.raises(ValueError, match="100.130"):
        parse_ziel_gruppe("abc.def")


def test_build_spec_requires_filter_and_registry(db_session, groups):
    with pytest.raises(ValueError, match="Umfang"):
        build_group_assign_spec(
            db_session, filters={"conditions": []}, ziel="100.130"
        )
    with pytest.raises(ValueError, match="fehlt"):
        build_group_assign_spec(
            db_session,
            filters={
                "conditions": [
                    {
                        "column": "article_number",
                        "operator": "starts_with",
                        "value": "060.020",
                    }
                ]
            },
            ziel="111.222",
        )
    spec = build_group_assign_spec(
        db_session,
        filters={
            "conditions": [
                {
                    "column": "article_number",
                    "operator": "starts_with",
                    "value": "060.020",
                }
            ]
        },
        ziel="884.131",
    )
    assert spec.kind == "group_assign"
    assert spec.pair == "884.131"
    assert spec.untergruppe_name == "ZielUG"


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_gruppen_zuordnen_proposes_without_write(db_session, snapshot, groups):
    args = GruppenZuordnenArgs.model_validate(
        {
            "filters": {
                "conditions": [
                    {
                        "column": "article_number",
                        "operator": "starts_with",
                        "value": "060.020",
                    }
                ]
            },
            "ziel_gruppe": "884.131",
        }
    )
    with patch("app.transform.preview.start_transform_preview") as preview:
        result = gruppen_zuordnen(db_session, args)
    preview.assert_not_called()
    assert result.total_count == 2
    assert result.rows[0]["spec"]["kind"] == "group_assign"
    assert MSG_NUMBERS_UNCHANGED in result.hinweis_de


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_gruppen_zuordnen_empty_scope(db_session, snapshot, groups):
    args = GruppenZuordnenArgs.model_validate(
        {"filters": {"conditions": []}, "ziel_gruppe": "884.131"}
    )
    result = gruppen_zuordnen(db_session, args)
    assert MSG_EMPTY_SCOPE in result.hinweis_de
    assert result.rows == []


def test_preview_sets_category_diff(db_session, snapshot, groups):
    spec = build_group_assign_spec(
        db_session,
        filters={
            "conditions": [
                {
                    "column": "article_number",
                    "operator": "starts_with",
                    "value": "060.020",
                }
            ]
        },
        ziel="884.131",
    )
    run = TransformRun(
        created_by_oid="oid",
        snapshot_id=snapshot.id,
        spec=spec.model_dump(mode="json"),
        status="previewing",
    )
    db_session.add(run)
    db_session.flush()

    client = MagicMock()
    categories = [
        {"id": "p100", "name": "ZielHG", "description": "884"},
        {
            "id": "c130",
            "name": "ZielUG",
            "description": "131",
            "parentCategoryId": "p100",
        },
        {"id": "p060", "name": "AltHG", "description": "060"},
        {
            "id": "old",
            "name": "Alt",
            "description": "020",
            "parentCategoryId": "p060",
        },
    ]
    articles = {
        "id-0": {
            "id": "id-0",
            "articleNumber": "060.020.0010",
            "version": "1",
            "articleCategoryId": "old",
        },
        "id-1": {
            "id": "id-1",
            "articleNumber": "060.020.0020",
            "version": "1",
            "articleCategoryId": "c130",
        },
    }

    def iter_pages(entity, *, params=None, page_size=None):
        if entity == "articleCategory":
            yield from categories
            return
        yield from articles.values()

    client.iter_pages.side_effect = iter_pages

    result = run_group_assign_preview(db_session, run, oid="oid", client=client)
    assert result["changed_rows"] == 1
    statuses = {row.article_number: row.row_status for row in run.rows}
    assert statuses["060.020.0010"] == "CHANGED"
    assert statuses["060.020.0020"] == "UNCHANGED"
    changed = next(row for row in run.rows if row.row_status == "CHANGED")
    assert changed.operations_fired[0]["new_id"] == "c130"
