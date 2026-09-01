"""POST /batches/{id}/edits: whitelist, raw_data immutability, numbering, transactions."""

from __future__ import annotations

import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.groups_service import create_hauptgruppe, create_untergruppe
from app.main import app
from app.models import ArticleBatch, ArticleBatchRow, Hauptgruppe
from core.article_payload import NUMBER_PLACEHOLDER

ACTOR = {"oid": "test-oid", "name": "Test User"}
PLAIN_USER = {
    "oid": "user-oid-batch",
    "name": "User",
    "email": "user@example.com",
    "roles": ["user"],
}


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


def _unused_code(db_session, prefix: str = "8") -> str:
    used = {row[0] for row in db_session.execute(select(Hauptgruppe.code)).all()}
    for index in range(100):
        code = f"{prefix}{index:02d}"
        if code not in used:
            return code
    raise RuntimeError("No free test code remaining")


def _raw_article(**overrides: str) -> dict[str, str]:
    data = {
        "Prosema-Artikelname": "Testartikel",
        "Einheit": "Stk.",
        "Artikeltyp": "BASIC",
        "Aktiv": "Ja",
        "Im Verkauf": "Ja",
        "Steuersatz": "STANDARD",
    }
    data.update(overrides)
    return data


def _make_batch(
    db_session,
    *,
    status: str = "draft",
    rows: list[dict[str, str]] | None = None,
    numbers: list[str] | None = None,
) -> tuple[ArticleBatch, list[ArticleBatchRow]]:
    from app.article_templates import get_active_template

    batch = ArticleBatch(
        status=status,
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        filename="test.csv",
        template_id=get_active_template(db_session).id,
    )
    db_session.add(batch)
    db_session.flush()
    created: list[ArticleBatchRow] = []
    payloads = rows or [_raw_article()]
    for index, raw in enumerate(payloads, start=1):
        number = ""
        if numbers and index <= len(numbers):
            number = numbers[index - 1]
        row = ArticleBatchRow(
            batch_id=batch.id,
            position=index,
            raw_data=dict(raw),
            edits={},
            proposed_article_number=number,
            include=True,
            validation_error="",
        )
        db_session.add(row)
        created.append(row)
    db_session.flush()
    return batch, created


def _raw_sql_data(db_session, row_id: uuid.UUID):
    return db_session.execute(
        text("SELECT raw_data FROM article_batch_rows WHERE id = CAST(:id AS uuid)"),
        {"id": str(row_id)},
    ).scalar()


def test_edits_without_groups_keeps_article_number_placeholder(user_client, db_session):
    batch, rows = _make_batch(db_session, rows=[_raw_article()])
    row = rows[0]
    assert row.proposed_article_number == ""
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[{"row_id": str(row.id), "field": "PROSEMA Kurztext", "value": "Neuer Name"}],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rows"][0]["proposed_article_number"] == NUMBER_PLACEHOLDER
    db_session.refresh(row)
    assert row.proposed_article_number == ""


def test_edits_rejects_non_whitelisted_field(user_client, db_session):
    batch, rows = _make_batch(db_session)
    row = rows[0]
    before = _raw_sql_data(db_session, row.id)
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[{"row_id": str(row.id), "field": "not_a_field", "value": "x"}],
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Feld nicht bearbeitbar"
    assert body["field"] == "not_a_field"
    db_session.refresh(row)
    assert row.edits == {}
    assert _raw_sql_data(db_session, row.id) == before


def test_edits_writes_edits_leaves_raw_data(user_client, db_session):
    batch, rows = _make_batch(db_session)
    row = rows[0]
    before = _raw_sql_data(db_session, row.id)
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[{"row_id": str(row.id), "field": "PROSEMA Kurztext", "value": "Neuer Name"}],
    )
    assert response.status_code == 200
    db_session.refresh(row)
    assert row.edits["PROSEMA Kurztext"] == "Neuer Name"
    assert _raw_sql_data(db_session, row.id) == before
    assert row.raw_data["Prosema-Artikelname"] == "Testartikel"


def test_edits_group_change_returns_new_article_number(user_client, db_session):
    code = _unused_code(db_session)
    haupt = create_hauptgruppe(db_session, code=code, name="Testhaupt", actor=ACTOR)
    create_untergruppe(db_session, haupt, code="001", name="Erste", actor=ACTOR)
    create_untergruppe(db_session, haupt, code="002", name="Zweite", actor=ACTOR)
    batch, rows = _make_batch(
        db_session,
        rows=[
            _raw_article(
                Hauptgruppe=f"Testhaupt - {code}",
                Untergruppe="Erste - 001",
            )
        ],
        numbers=[f"{code}.001.0010"],
    )
    row = rows[0]
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[{"row_id": str(row.id), "field": "Untergruppe", "value": "Zweite - 002"}],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rows"][0]["proposed_article_number"] == f"{code}.002.0010"
    db_session.refresh(row)
    assert row.proposed_article_number == f"{code}.002.0010"
    assert row.edits["Untergruppe"] == "Zweite - 002"


def test_edits_hauptgruppe_change_clears_foreign_untergruppe(user_client, db_session):
    code_a = _unused_code(db_session, prefix="7")
    code_b = _unused_code(db_session, prefix="6")
    haupt_a = create_hauptgruppe(db_session, code=code_a, name="Alpha", actor=ACTOR)
    haupt_b = create_hauptgruppe(db_session, code=code_b, name="Beta", actor=ACTOR)
    create_untergruppe(db_session, haupt_a, code="010", name="KindA", actor=ACTOR)
    create_untergruppe(db_session, haupt_b, code="020", name="KindB", actor=ACTOR)
    batch, rows = _make_batch(
        db_session,
        rows=[
            _raw_article(
                Hauptgruppe=f"Alpha - {code_a}",
                Untergruppe="KindA - 010",
            )
        ],
        numbers=[f"{code_a}.010.0010"],
    )
    row = rows[0]
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[
            {
                "row_id": str(row.id),
                "field": "Hauptgruppe",
                "value": f"Beta - {code_b}",
            }
        ],
    )
    assert response.status_code == 200
    body = response.json()["rows"][0]
    assert body["corrected"]["Untergruppe"] == ""
    assert "Untergruppe fehlt" in body["validation_error"]
    db_session.refresh(row)
    assert row.edits["Hauptgruppe"] == f"Beta - {code_b}"
    assert row.edits["Untergruppe"] == ""


def test_grid_config_untergruppe_map_follows_registry(user_client, db_session):
    code_a = _unused_code(db_session, prefix="5")
    code_b = _unused_code(db_session, prefix="4")
    haupt_a = create_hauptgruppe(db_session, code=code_a, name="HolzMap", actor=ACTOR)
    haupt_b = create_hauptgruppe(db_session, code=code_b, name="MetallMap", actor=ACTOR)
    create_untergruppe(db_session, haupt_a, code="011", name="Bretter", actor=ACTOR)
    create_untergruppe(db_session, haupt_b, code="022", name="Schrauben", actor=ACTOR)
    batch, _rows = _make_batch(db_session)
    response = user_client.get(f"/batches/{batch.id}")
    assert response.status_code == 200
    match = re.search(
        r'<script type="application/json" id="batch-grid-config">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    assert match is not None
    config = json.loads(match.group(1))
    mapping = config["untergruppeByHauptgruppe"]
    label_a = f"HolzMap - {code_a}"
    label_b = f"MetallMap - {code_b}"
    assert mapping[label_a] == ["Bretter - 011"]
    assert mapping[label_b] == ["Schrauben - 022"]
    assert "Schrauben - 022" not in mapping[label_a]
    assert "Bretter - 011" not in mapping[label_b]
    js = user_client.get("/static/batch_grid.js")
    assert js.status_code == 200
    assert "attachUntergruppeFilter" in js.text
    assert "untergruppeByHauptgruppe" in js.text


def test_edits_accepts_registry_group_missing_from_weclapp_schema(user_client, db_session):
    code = _unused_code(db_session, prefix="3")
    haupt = create_hauptgruppe(db_session, code=code, name="Bauchemie", actor=ACTOR)
    create_untergruppe(db_session, haupt, code="020", name="Pflasterfugenmörtel", actor=ACTOR)
    label_h = f"Bauchemie - {code}"
    label_u = "Pflasterfugenmörtel - 020"
    batch, rows = _make_batch(
        db_session,
        rows=[_raw_article(Hauptgruppe=label_h, Untergruppe=label_u)],
    )
    row = rows[0]
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[
            {"row_id": str(row.id), "field": "Hauptgruppe", "value": label_h},
            {"row_id": str(row.id), "field": "Untergruppe", "value": label_u},
        ],
    )
    assert response.status_code == 200
    body = response.json()["rows"][0]
    error = body["validation_error"] or ""
    assert "Ungültiger Wert" not in error
    assert "Hauptwarengruppe" not in error
    assert body["proposed_article_number"].startswith(f"{code}.020.")

    page = user_client.get(f"/batches/{batch.id}")
    assert page.status_code == 200
    match = re.search(
        r'<script type="application/json" id="batch-grid-config">(.*?)</script>',
        page.text,
        re.DOTALL,
    )
    assert match is not None
    config = json.loads(match.group(1))
    haupt_col = next(col for col in config["columns"] if col["name"] == "Hauptgruppe")
    unter_col = next(col for col in config["columns"] if col["name"] == "Untergruppe")
    assert label_h in haupt_col["source"]
    assert label_u in unter_col["source"]
    assert config["untergruppeByHauptgruppe"][label_h] == [label_u]


def test_grid_reload_clears_stale_weclapp_group_list_error(user_client, db_session):
    code = _unused_code(db_session, prefix="2")
    haupt = create_hauptgruppe(db_session, code=code, name="Bauchemie", actor=ACTOR)
    create_untergruppe(db_session, haupt, code="020", name="Pflasterfugenmörtel", actor=ACTOR)
    label_h = f"Bauchemie - {code}"
    label_u = "Pflasterfugenmörtel - 020"
    batch, rows = _make_batch(
        db_session,
        rows=[_raw_article(Hauptgruppe=label_h, Untergruppe=label_u)],
        numbers=[f"{code}.020.0010"],
    )
    row = rows[0]
    row.validation_error = "Ungültiger Wert für Hauptwarengruppe (Auswahl): Bauchemie - 130"
    db_session.flush()

    response = user_client.get(f"/batches/{batch.id}")
    assert response.status_code == 200
    db_session.refresh(row)
    assert "Ungültiger Wert" not in (row.validation_error or "")
    assert "Hauptwarengruppe" not in (row.validation_error or "")


def test_edits_rejects_approved_batch(user_client, db_session):
    batch, rows = _make_batch(db_session, status="approved")
    row = rows[0]
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[{"row_id": str(row.id), "field": "PROSEMA Kurztext", "value": "Nope"}],
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Stapel bereits genehmigt — keine Änderungen möglich"
    db_session.refresh(row)
    assert row.edits == {}


def test_edits_200_applied_atomically(user_client, db_session):
    payloads = [_raw_article(**{"Prosema-Artikelname": f"Alt {i}"}) for i in range(200)]
    batch, rows = _make_batch(db_session, rows=payloads)
    mixed = [
        {"row_id": str(row.id), "field": "PROSEMA Kurztext", "value": f"Neu {i}"}
        for i, row in enumerate(rows)
    ]
    mixed[-1]["field"] = "geheimes_feld"
    blocked = user_client.post(f"/batches/{batch.id}/edits", json=mixed)
    assert blocked.status_code == 400
    assert blocked.json()["field"] == "geheimes_feld"
    for row in rows:
        db_session.refresh(row)
        assert row.edits == {}

    ok = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[
            {"row_id": str(row.id), "field": "PROSEMA Kurztext", "value": f"Neu {i}"}
            for i, row in enumerate(rows)
        ],
    )
    assert ok.status_code == 200
    assert len(ok.json()["rows"]) == 200
    for i, row in enumerate(rows):
        db_session.refresh(row)
        assert row.edits["PROSEMA Kurztext"] == f"Neu {i}"


def test_edits_stores_leading_equals_literally(user_client, db_session):
    batch, rows = _make_batch(db_session)
    row = rows[0]
    formula = "=SUM(A1:A2)"
    response = user_client.post(
        f"/batches/{batch.id}/edits",
        json=[{"row_id": str(row.id), "field": "PROSEMA Langtext", "value": formula}],
    )
    assert response.status_code == 200
    db_session.refresh(row)
    assert row.edits["PROSEMA Langtext"] == formula
    assert row.edits["PROSEMA Langtext"].startswith("=")


def test_batch_grid_page_uses_vendored_jspreadsheet(user_client, db_session):
    batch, _rows = _make_batch(db_session)
    response = user_client.get(f"/batches/{batch.id}")
    assert response.status_code == 200
    html = response.text
    assert 'src="/static/jspreadsheet.js"' in html
    assert 'href="/static/jspreadsheet.css"' in html
    assert 'src="/static/jsuites.js"' in html
    assert 'href="/static/jsuites.css"' in html
    assert "cdn.jsdelivr.net" not in html
    assert "bossanova.uk" not in html
    assert "jsuites.net" not in html
    assert "parseFormulas" in html
    assert "worksheets" in html or "batch-grid-config" in html
    assert "Gefiltert:" in html
    assert "Gespeichert" in html
    match = re.search(
        r'<script type="application/json" id="batch-grid-config">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    config = json.loads(match.group(1))
    assert config["parseFormulas"] is False
    assert config["freezeColumns"] == 3
    by_name = {column["name"]: column for column in config["columns"]}
    assert by_name["Prosema Artikelnummer"]["readOnly"] is True
    assert by_name["Einheit"]["type"] == "dropdown"
    assert "Stk." in by_name["Einheit"]["source"]
    assert by_name["Hauptgruppe"]["type"] == "dropdown"
    js = user_client.get("/static/jspreadsheet.js")
    css = user_client.get("/static/jspreadsheet.css")
    suites = user_client.get("/static/jsuites.js")
    suites_css = user_client.get("/static/jsuites.css")
    assert js.status_code == 200
    assert css.status_code == 200
    assert suites.status_code == 200
    assert suites_css.status_code == 200
    assert "cdn.jsdelivr.net" not in js.text[:500]
    presence = user_client.post(f"/batches/{batch.id}/anwesenheit")
    assert presence.status_code == 200
    assert "Auch geöffnet" not in presence.text
