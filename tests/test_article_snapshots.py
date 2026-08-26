"""Artikel-Übersicht: snapshot pull, filtering, Excel, retention."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.jobs import HANDLERS
from app.main import app
from app.models import ArticleSnapshot, ArticleSnapshotRow, Job
from app.snapshots import (
    SnapshotFilters,
    build_grid_config,
    count_filtered_rows,
    fetch_filtered_rows,
    pull_snapshot_rows,
)
from core.article_flatten import build_snapshot_columns, extract_indexed_fields, master_row_to_snapshot_data

PLAIN_USER = {
    "oid": "user-oid-snapshots",
    "name": "Christopher Kolloff",
    "email": "user@example.com",
    "roles": ["user"],
}

TENANT = "test-tenant"


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
def user_client(db_session):
    def override_user():
        return PLAIN_USER

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def _sample_master(article_number: str, **extra: str) -> dict[str, str]:
    from scripts.weclapp.master_columns import EXPORT_COLUMNS

    row = {column: "" for column in EXPORT_COLUMNS}
    row["Prosema Artikelnummer"] = article_number
    row["PROSEMA Kurztext"] = extra.get("name", f"Artikel {article_number}")
    row["Hauptgruppe"] = extra.get("hauptgruppe", "Holz - 010")
    row["Untergruppe"] = extra.get("untergruppe", "Bretter - 020")
    row["weclapp Aktiv"] = extra.get("aktiv", "Ja")
    row["weclapp Artikel-ID"] = extra.get("weclapp_id", f"id-{article_number}")
    row["weclapp Version"] = extra.get("version", "42")
    return row


def _make_complete_snapshot(
    db_session,
    *,
    rows: list[dict[str, str]] | None = None,
    columns: list[dict] | None = None,
) -> ArticleSnapshot:
    if rows is None:
        rows = [
            master_row_to_snapshot_data(_sample_master("010.020.0010", hauptgruppe="Holz - 010")),
            master_row_to_snapshot_data(
                _sample_master(
                    "010.030.0001",
                    hauptgruppe="Holz - 010",
                    untergruppe="Latten - 030",
                    aktiv="Nein",
                )
            ),
            master_row_to_snapshot_data(
                _sample_master(
                    "020.010.0005",
                    hauptgruppe="Metall - 020",
                    untergruppe="Schrauben - 010",
                )
            ),
        ]
    columns = columns or build_snapshot_columns(rows)
    snapshot = ArticleSnapshot(
        status="complete",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        weclapp_tenant=TENANT,
        row_count=len(rows),
        columns=columns,
    )
    db_session.add(snapshot)
    db_session.flush()
    for position, data in enumerate(rows):
        fields = extract_indexed_fields(data)
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snapshot.id,
                position=position,
                data=data,
                article_number=fields["article_number"],
                article_name=fields["article_name"],
                hauptgruppe_code=fields["hauptgruppe_code"],
                untergruppe_code=fields["untergruppe_code"],
                active=fields["active"],
                weclapp_id=fields["weclapp_id"],
                weclapp_version=fields["weclapp_version"],
            )
        )
    db_session.flush()
    return snapshot


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_worker_writes_rows_in_one_transaction_and_failure_leaves_no_rows(db_session):
    snapshot = ArticleSnapshot(
        status="running",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        weclapp_tenant=TENANT,
    )
    db_session.add(snapshot)
    db_session.commit()

    articles = [
        {"id": "1", "articleNumber": "010.020.0010", "name": "A", "version": 1},
        {"id": "2", "articleNumber": "010.020.0011", "name": "B", "version": 2},
    ]
    client = MagicMock()

    with patch("app.weclapp.weclapp_client_for", return_value=client):
        with patch("app.snapshots.flatten_articles") as flat_mock:
            data_rows = [
                master_row_to_snapshot_data(_sample_master("010.020.0010")),
                master_row_to_snapshot_data(_sample_master("010.020.0011")),
            ]
            indexed = [extract_indexed_fields(row) for row in data_rows]
            columns = build_snapshot_columns(data_rows)
            flat_mock.return_value = (data_rows, indexed, columns)
            result = pull_snapshot_rows(db_session, snapshot, oid=PLAIN_USER["oid"])

    assert result["row_count"] == 2
    db_session.refresh(snapshot)
    assert snapshot.status == "complete"
    assert snapshot.row_count == 2
    assert db_session.scalar(select(func.count()).select_from(ArticleSnapshotRow)) == 2

    failing = ArticleSnapshot(
        status="running",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        weclapp_tenant=TENANT,
    )
    db_session.add(failing)
    db_session.commit()

    boom = MagicMock()
    boom.iter_pages.side_effect = RuntimeError("pull aborted")

    from app.snapshots import fail_snapshot

    with patch("app.weclapp.weclapp_client_for", return_value=boom):
        try:
            pull_snapshot_rows(db_session, failing, oid=PLAIN_USER["oid"])
        except RuntimeError:
            db_session.rollback()
            failing = db_session.get(ArticleSnapshot, failing.id)
            fail_snapshot(db_session, failing, "pull aborted")

    db_session.refresh(failing)
    assert failing.status == "failed"
    assert failing.error == "pull aborted"
    assert (
        db_session.scalar(
            select(func.count()).where(ArticleSnapshotRow.snapshot_id == failing.id)
        )
        == 0
    )


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_post_abfragen_while_running_does_not_enqueue_second_job(db_session, user_client):
    running = ArticleSnapshot(
        status="running",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        weclapp_tenant=TENANT,
    )
    db_session.add(running)
    db_session.commit()

    before = db_session.scalar(select(func.count()).select_from(Job))
    response = user_client.post("/artikel-uebersicht/abfragen", follow_redirects=False)
    after = db_session.scalar(select(func.count()).select_from(Job))
    assert after == before
    assert response.status_code == 303
    assert str(running.id) in response.headers["location"]


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_stand_banner_fresh_pull_is_green_list_link_is_yellow(db_session, user_client):
    snapshot = _make_complete_snapshot(db_session)
    db_session.commit()

    fresh = user_client.get(f"/artikel-uebersicht/{snapshot.id}?neu=1")
    assert fresh.status_code == 200
    assert "snapshot-stand-banner--current" in fresh.text
    assert "snapshot-stand-banner__close" in fresh.text

    from_list = user_client.get(f"/artikel-uebersicht/{snapshot.id}")
    assert from_list.status_code == 200
    assert "snapshot-stand-banner--archive" in from_list.text
    assert "snapshot-stand-banner__close" not in from_list.text


@patch("app.routes.snapshots.create_snapshot_pull")
@patch("app.config.settings.weclapp_tenant", TENANT)
def test_post_abfragen_redirects_with_fresh_pull_flag(pull_mock, user_client):
    snapshot_id = uuid.uuid4()
    snapshot = ArticleSnapshot(
        id=snapshot_id,
        status="running",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        weclapp_tenant=TENANT,
    )
    pull_mock.return_value = (snapshot, MagicMock())

    response = user_client.post("/artikel-uebersicht/abfragen", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/artikel-uebersicht/{snapshot_id}?neu=1"


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_filter_hauptgruppe_matches_count(db_session, user_client):
    snapshot = _make_complete_snapshot(db_session)
    db_session.commit()

    response = user_client.get(
        f"/artikel-uebersicht/{snapshot.id}/zeilen?hauptgruppe=010&nur_aktive=0"
    )
    assert response.status_code == 200
    assert "Gefiltert: 2 von 3 Zeilen" in response.text

    filters = SnapshotFilters(hauptgruppe="010", nur_aktive=False)
    assert count_filtered_rows(db_session, snapshot.id, filters) == 2
    rows, total, _pages = fetch_filtered_rows(db_session, snapshot.id, filters)
    assert total == 2
    assert len(rows) == 2
    assert all(row.hauptgruppe_code == "010" for row in rows)


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_untergruppe_options_narrow_by_hauptgruppe(db_session, user_client):
    snapshot = _make_complete_snapshot(db_session)
    db_session.commit()

    response = user_client.get(
        f"/artikel-uebersicht/{snapshot.id}/untergruppen?hauptgruppe=010"
    )
    assert response.status_code == 200
    assert 'name="untergruppe"' in response.text
    # Holz (010) has Bretter→020 and Latten→030 only.
    assert ">020<" in response.text
    assert ">030<" in response.text
    assert ">010<" not in response.text

    all_groups = user_client.get(f"/artikel-uebersicht/{snapshot.id}/untergruppen")
    assert ">020<" in all_groups.text
    assert ">030<" in all_groups.text
    assert ">010<" in all_groups.text


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_excel_matches_zeilen_filter(db_session, user_client):
    snapshot = _make_complete_snapshot(db_session)
    db_session.commit()

    zeilen = user_client.get(f"/artikel-uebersicht/{snapshot.id}/zeilen?hauptgruppe=020")
    assert "Gefiltert: 1 von 3 Zeilen" in zeilen.text

    excel = user_client.get(f"/artikel-uebersicht/{snapshot.id}/excel?hauptgruppe=020")
    assert excel.status_code == 200
    wb = load_workbook(io.BytesIO(excel.content))
    ws = wb["Artikel"]
    headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
    artikel_col = headers.index("Prosema Artikelnummer") + 1
    numbers = {ws.cell(row, artikel_col).value for row in range(2, ws.max_row + 1)}
    assert numbers == {"020.010.0005"}


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_article_number_excel_text_format(db_session, user_client):
    snapshot = _make_complete_snapshot(db_session)
    db_session.commit()

    response = user_client.get(f"/artikel-uebersicht/{snapshot.id}/excel")
    wb = load_workbook(io.BytesIO(response.content))
    ws = wb["Artikel"]
    headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
    artikel_col = headers.index("Prosema Artikelnummer") + 1
    cell = ws.cell(2, artikel_col)
    assert cell.number_format == "@"
    assert cell.value == "010.020.0010"
    assert isinstance(cell.value, str)


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_snapshot_uses_stored_columns_not_current_schema(db_session):
    stored_columns = [
        {"key": "Legacy-Spalte", "title": "Legacy-Spalte", "width": 120},
        {"key": "Prosema Artikelnummer", "title": "Prosema Artikelnummer", "width": 160},
    ]
    data = {"Legacy-Spalte": "alt", "Prosema Artikelnummer": "010.020.0010"}
    snapshot = ArticleSnapshot(
        status="complete",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        weclapp_tenant=TENANT,
        row_count=1,
        columns=stored_columns,
    )
    db_session.add(snapshot)
    db_session.flush()
    row = ArticleSnapshotRow(
        snapshot_id=snapshot.id,
        position=0,
        data=data,
        article_number="010.020.0010",
        article_name="Test",
        hauptgruppe_code="010",
        untergruppe_code="020",
        active=True,
        weclapp_id="1",
    )
    db_session.add(row)
    db_session.flush()

    config = build_grid_config(snapshot, [row])
    assert config["fields"] == ["Legacy-Spalte", "Prosema Artikelnummer"]
    assert config["data"] == [["alt", "010.020.0010"]]


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_snapshot_routes_never_write_to_weclapp(db_session):
    snapshot = ArticleSnapshot(
        status="running",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        weclapp_tenant=TENANT,
    )
    db_session.add(snapshot)
    db_session.commit()

    client = MagicMock()
    client.iter_pages.return_value = []
    client.get.return_value = {}
    client.post = MagicMock()
    client.put = MagicMock()

    with patch("app.weclapp.weclapp_client_for", return_value=client):
        pull_snapshot_rows(db_session, snapshot, oid=PLAIN_USER["oid"])

    client.post.assert_not_called()
    client.put.assert_not_called()


@patch("app.config.settings.weclapp_tenant", TENANT)
def test_retention_deletes_21st_oldest_snapshot(db_session):
    from datetime import UTC, datetime, timedelta

    ids: list[uuid.UUID] = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(21):
        snap = ArticleSnapshot(
            status="complete",
            created_by_oid=PLAIN_USER["oid"],
            created_by_name=PLAIN_USER["name"],
            weclapp_tenant=TENANT,
            row_count=1,
            created_at=base + timedelta(minutes=index),
            columns=[
                {"key": "Prosema Artikelnummer", "title": "Prosema Artikelnummer", "width": 160}
            ],
        )
        db_session.add(snap)
        db_session.flush()
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snap.id,
                position=0,
                data={"Prosema Artikelnummer": f"n-{index}"},
                article_number=f"n-{index}",
                article_name="x",
                hauptgruppe_code="010",
                untergruppe_code="020",
                active=True,
                weclapp_id=str(index),
            )
        )
        ids.append(snap.id)
    db_session.commit()

    from app.snapshots import apply_retention

    deleted = apply_retention(db_session, tenant=TENANT)
    db_session.commit()

    assert len(deleted) == 1
    assert deleted[0] == ids[0]
    remaining = list(db_session.scalars(select(ArticleSnapshot)))
    assert len(remaining) == 20
    assert db_session.get(ArticleSnapshot, ids[0]) is None
    assert db_session.scalar(select(func.count()).select_from(ArticleSnapshotRow)) == 20


def test_job_handler_registered():
    assert "weclapp_article_snapshot" in HANDLERS
