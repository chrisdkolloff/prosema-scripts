"""Per-user weclapp tokens: encryption, client construction, errors, jobs, HTML."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.jobs import HANDLERS, _execute_job, job_handler
from app.main import app
from app.models import Job
from app.weclapp import (
    LANDING_TOOLS,
    MSG_INVALID,
    MSG_NO_LICENCE,
    MSG_NO_TOKEN,
    NoWeclappToken,
    WeclappLicenceMissing,
    WeclappTokenInvalid,
    decrypt_token,
    encrypt_token,
    map_weclapp_error,
    store_token,
    weclapp_client_for,
)
from scripts.weclapp.client import WeclappError

PLAIN_USER = {
    "oid": "user-oid-weclapp",
    "name": "User",
    "email": "user@example.com",
    "roles": ["user"],
}

SECRET_TOKEN = "tok_TEST_PLAINTEXT_DO_NOT_ECHO_9f3a"


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


def test_encrypt_decrypt_roundtrip():
    key = Fernet.generate_key()
    plaintext = "roundtrip-token-value"
    assert decrypt_token(encrypt_token(plaintext, key), key) == plaintext


def test_weclapp_client_for_without_row_raises(db_session):
    with pytest.raises(NoWeclappToken, match=MSG_NO_TOKEN):
        weclapp_client_for(db_session, "oid-without-token")


def test_map_401_is_invalid_token():
    err = WeclappError("denied", status_code=401)
    mapped = map_weclapp_error(err)
    assert isinstance(mapped, WeclappTokenInvalid)
    assert str(mapped) == MSG_INVALID


def test_map_403_is_missing_licence():
    err = WeclappError("forbidden", status_code=403)
    mapped = map_weclapp_error(err)
    assert isinstance(mapped, WeclappLicenceMissing)
    assert str(mapped) == MSG_NO_LICENCE


def test_store_then_client_decrypts_original(db_session):
    store_token(db_session, PLAIN_USER["oid"], SECRET_TOKEN)
    client = weclapp_client_for(db_session, PLAIN_USER["oid"])
    assert client.config.api_token == SECRET_TOKEN


def test_job_without_token_fails_without_killing_worker(db_session):
    name = "needs_weclapp_token"

    @job_handler(name)
    def handler(db, _payload, oid):
        weclapp_client_for(db, oid)
        return {}

    job = Job(
        id=uuid.uuid4(),
        job_type=name,
        payload={"note": "no token here"},
        status="running",
        created_by_oid="oid-without-token",
        created_by_name="Christopher Test",
    )
    db_session.add(job)
    db_session.flush()
    try:
        _execute_job(db_session, job)
        assert job.status == "failed"
        assert job.error == MSG_NO_TOKEN
        assert "Traceback" not in (job.error or "")
        _execute_job(db_session, job)
        assert job.status == "failed"
    finally:
        HANDLERS.pop(name, None)


def test_job_403_uses_licence_message(db_session):
    name = "needs_weclapp_licence"
    store_token(db_session, PLAIN_USER["oid"], SECRET_TOKEN)

    @job_handler(name)
    def handler(db, _payload, oid):
        client = weclapp_client_for(db, oid)
        client.get("/currency", params={"pageSize": 1})
        return {}

    job = Job(
        id=uuid.uuid4(),
        job_type=name,
        payload={},
        status="running",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
    )
    db_session.add(job)
    db_session.flush()
    try:
        with patch(
            "scripts.weclapp.client.WeclappClient.get",
            side_effect=WeclappError("forbidden", status_code=403),
        ):
            _execute_job(db_session, job)
        assert job.status == "failed"
        assert job.error == MSG_NO_LICENCE
    finally:
        HANDLERS.pop(name, None)


def test_settings_page_does_not_render_stored_token(user_client, db_session):
    store_token(db_session, PLAIN_USER["oid"], SECRET_TOKEN)
    response = user_client.get("/einstellungen")
    assert response.status_code == 200
    assert SECRET_TOKEN not in response.text
    assert "Externe Systeme" in response.text
    assert "Anwendung" in response.text
    assert "weclapp" in response.text
    assert "Token hinterlegt" in response.text
    assert 'type="password"' in response.text
    post = user_client.post(
        "/einstellungen/weclapp",
        data={"token": SECRET_TOKEN},
        follow_redirects=True,
    )
    assert post.status_code == 200
    assert SECRET_TOKEN not in post.text
    redirected = user_client.get("/einstellungen/weclapp", follow_redirects=False)
    assert redirected.status_code == 303
    assert redirected.headers["location"] == "/einstellungen"


def test_gruppen_work_without_weclapp_token(user_client):
    listing = user_client.get("/gruppen")
    assert listing.status_code == 200
    assert MSG_NO_TOKEN not in listing.text
    assert MSG_NO_LICENCE not in listing.text
    assert "weclapp-Lizenz" not in listing.text
    diagram = user_client.get("/gruppen/diagramm")
    assert diagram.status_code == 200
    assert MSG_NO_TOKEN not in diagram.text


def test_landing_lists_every_tool(user_client):
    response = user_client.get("/")
    assert response.status_code == 200
    assert "Externe Systeme" in response.text
    assert "Anwendung" in response.text
    assert "weclapp" in response.text
    assert ">Beschreibung<" in response.text
    for tool in LANDING_TOOLS:
        assert tool["name"] in response.text
        assert tool["description"] in response.text
        assert f'href="{tool["href"]}"' in response.text
    assert "d-none d-md-table-cell" in response.text
    systems = response.text.split("Werkzeuge", 1)[0]
    assert ">Beschreibung<" not in systems
    fragment = user_client.get("/weclapp/status")
    assert fragment.status_code == 200
    assert "<td>weclapp</td>" in fragment.text
    assert "Kein Token hinterlegt" in fragment.text
    assert "Externe Systeme" in fragment.text
    assert 'class="system-status-detail"' in fragment.text
    assert ">Beschreibung<" in fragment.text
    for tool in LANDING_TOOLS:
        assert tool["description"] in fragment.text
    fragment_systems = fragment.text.split("Werkzeuge", 1)[0]
    assert ">Beschreibung<" not in fragment_systems
    assert "Nicht verfügbar" not in fragment.text
    assert fragment.text.count("Aktualisieren nicht möglich") == sum(
        1
        for tool in LANDING_TOOLS
        if tool["needs_weclapp"] or tool["refresh_needs_weclapp"]
    )


def test_active_jobs_banner_names_triggering_user(user_client, db_session):
    job = Job(
        id=uuid.uuid4(),
        job_type="noop",
        payload={},
        status="queued",
        created_by_oid="other-oid",
        created_by_name="Christopher Kara",
    )
    db_session.add(job)
    db_session.flush()
    response = user_client.get("/jobs/aktiv")
    assert response.status_code == 200
    assert "Läuft: Testlauf (Christopher Kara)" in response.text
    assert "weclapp-Lizenz bitte noch nicht übergeben" in response.text


def test_active_jobs_banner_snapshot_is_in_bearbeitung(user_client, db_session):
    job = Job(
        id=uuid.uuid4(),
        job_type="weclapp_article_snapshot",
        payload={},
        status="running",
        created_by_oid="other-oid",
        created_by_name="Christopher Kara",
    )
    db_session.add(job)
    db_session.flush()
    response = user_client.get("/jobs/aktiv")
    assert response.status_code == 200
    assert "Artikelabfrage in Bearbeitung..." in response.text
    assert "weclapp-Lizenz bitte noch nicht übergeben" not in response.text
