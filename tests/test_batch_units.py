"""Article-registration Einheit comes from weclapp_units, not only schema JSON."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.main import app
from app.models import ArticleBatch, ArticleBatchRow, UserWeclappToken, WeclappUnit
from app.weclapp import encrypt_token
from scripts.weclapp.article_import import LookupTables, _load_schema
from scripts.weclapp.client import WeclappError

PLAIN_USER = {
    "oid": "unit-create-oid",
    "name": "Unit User",
    "email": "unit@example.com",
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


@pytest.fixture(autouse=True)
def _reset_schema_lookups_cache():
    import app.batches as batches_mod

    batches_mod._LOOKUPS = None
    yield
    batches_mod._LOOKUPS = None


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


def _schema_without_names(*names: str) -> LookupTables:
    schema = _load_schema()
    blocked = {n.casefold() for n in names}
    schema["lookups"]["units"] = [
        unit
        for unit in (schema.get("lookups") or {}).get("units") or []
        if str(unit.get("name") or "").casefold() not in blocked
        and str(unit.get("description") or "").casefold() not in blocked
    ]
    return LookupTables(schema)


def _store_token(db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(
        UserWeclappToken(
            oid=PLAIN_USER["oid"],
            token_encrypted=encrypt_token("test-token"),
            created_at=now,
            updated_at=now,
            last_verified_ok=True,
            last_verified_at=now,
        )
    )
    db_session.flush()


def _make_batch_with_unit(
    db_session: Session, *, einheit: str, status: str = "draft"
) -> tuple[ArticleBatch, ArticleBatchRow]:
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
    row = ArticleBatchRow(
        batch_id=batch.id,
        position=1,
        raw_data={
            "Prosema-Artikelname": "Testartikel",
            "Einheit": einheit,
            "Artikeltyp": "STORABLE",
            "Aktiv": "Ja",
            "Im Verkauf": "Ja",
            "Steuersatz": "STANDARD",
        },
        edits={},
        proposed_article_number="130.010.001",
        include=True,
        validation_error=f"Unbekannte Einheit: {einheit}",
    )
    db_session.add(row)
    db_session.flush()
    return batch, row


def test_db_unit_resolves_when_absent_from_schema(db_session):
    import app.batches as batches_mod
    from app.batches import lookups_for_db, schema_dropdowns, validate_effective

    batches_mod._LOOKUPS = _schema_without_names("Fass")
    assert "fass" not in batches_mod._LOOKUPS.units_by_key

    db_session.add(
        WeclappUnit(
            weclapp_id="999001",
            name="Fass",
            description="Fass",
            last_seen_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    lookups = lookups_for_db(db_session)
    assert lookups.unit_id("Fass") == "999001"
    assert "Fass" in schema_dropdowns(db_session)["Einheit"]

    values = {
        "Prosema-Artikelnummer": "130.010.001",
        "Prosema-Artikelname": "Testfass",
        "Einheit": "Fass",
        "Artikeltyp": "STORABLE",
        "Aktiv": "Ja",
        "Im Verkauf": "Ja",
        "Steuersatz": "STANDARD",
    }
    assert validate_effective(values, None, lookups=lookups) == ""


def test_unknown_unit_still_rejected(db_session):
    from app.batches import lookups_for_db, validate_effective

    lookups = lookups_for_db(db_session)
    with pytest.raises(ValueError, match="Unbekannte Einheit"):
        lookups.unit_id("NichtVorhandenXYZ")

    values = {
        "Prosema-Artikelnummer": "130.010.001",
        "Prosema-Artikelname": "Test",
        "Einheit": "NichtVorhandenXYZ",
        "Artikeltyp": "STORABLE",
        "Aktiv": "Ja",
        "Im Verkauf": "Ja",
        "Steuersatz": "STANDARD",
    }
    error = validate_effective(values, None, lookups=lookups)
    assert "Unbekannte Einheit" in error
    assert "NichtVorhandenXYZ" in error


def test_replace_units_and_with_units_share_categories():
    base = LookupTables(_load_schema())
    assert base.category_names
    overlay = base.with_units(
        [{"id": "1", "name": "Eimer", "description": "Eimer"}]
    )
    assert overlay.unit_id("Eimer") == "1"
    assert overlay.unit_id("eimer") == "1"
    assert overlay.category_names == base.category_names
    assert overlay.attrs_by_label is base.attrs_by_label
    with pytest.raises(ValueError, match="Unbekannte Einheit"):
        overlay.unit_id("Stk.")


def test_create_unit_posts_and_clears_validation(user_client, db_session):
    _store_token(db_session)
    batch, row = _make_batch_with_unit(db_session, einheit="NeuEinheit")
    client = MagicMock()
    client.post.return_value = {
        "id": "900001",
        "name": "NeuEinheit",
        "description": "NeuEinheit",
    }

    with patch("app.batch_units.weclapp_client_for", return_value=client):
        response = user_client.post(
            f"/batches/{batch.id}/einheit-anlegen",
            json={"name": "NeuEinheit"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["unit"] == {"id": "900001", "name": "NeuEinheit"}
    client.post.assert_called_once_with(
        "/unit", json={"name": "NeuEinheit", "description": "NeuEinheit"}
    )
    stored = db_session.get(WeclappUnit, "900001")
    assert stored is not None
    assert stored.name == "NeuEinheit"
    db_session.refresh(row)
    assert "Unbekannte Einheit" not in (row.validation_error or "")
    assert body["rows"][0]["id"] == str(row.id)
    assert "Unbekannte Einheit" not in body["rows"][0]["validation_error"]


def test_create_unit_reuses_catalogue_without_post(user_client, db_session):
    _store_token(db_session)
    db_session.add(
        WeclappUnit(
            weclapp_id="900002",
            name="Vorhanden",
            description="Vorhanden",
            last_seen_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    batch, row = _make_batch_with_unit(db_session, einheit="Vorhanden")
    client = MagicMock()

    with patch("app.batch_units.weclapp_client_for", return_value=client):
        response = user_client.post(
            f"/batches/{batch.id}/einheit-anlegen",
            json={"name": "Vorhanden"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is False
    assert body["unit"]["id"] == "900002"
    client.post.assert_not_called()
    db_session.refresh(row)
    assert "Unbekannte Einheit" not in (row.validation_error or "")


def test_create_unit_weclapp_failure_leaves_error(user_client, db_session):
    _store_token(db_session)
    batch, row = _make_batch_with_unit(db_session, einheit="Kaputt")
    before = row.validation_error
    client = MagicMock()
    client.post.side_effect = WeclappError("unit boom", status_code=400)

    with patch("app.batch_units.weclapp_client_for", return_value=client):
        response = user_client.post(
            f"/batches/{batch.id}/einheit-anlegen",
            json={"name": "Kaputt"},
        )

    assert response.status_code == 400
    assert "unit boom" in response.json()["error"]
    db_session.refresh(row)
    assert row.validation_error == before
    assert db_session.get(WeclappUnit, "Kaputt") is None


def test_create_unit_rejects_submitted(user_client, db_session):
    _store_token(db_session)
    batch, _row = _make_batch_with_unit(
        db_session, einheit="X", status="submitted"
    )
    response = user_client.post(
        f"/batches/{batch.id}/einheit-anlegen",
        json={"name": "X"},
    )
    assert response.status_code == 409


def test_grid_config_exposes_weclapp_gate(db_session):
    from app.batches import build_grid_config

    batch, _row = _make_batch_with_unit(db_session, einheit="Stk.")
    off = build_grid_config(db_session, batch, [_row], weclapp_ok=False)
    assert off["weclappOk"] is False
    assert off["settingsPath"] == "/einstellungen"
    assert off["createUnitUrl"].endswith("/einheit-anlegen")
    on = build_grid_config(
        db_session,
        batch,
        [_row],
        weclapp_ok=True,
        settings_path="/einstellungen",
    )
    assert on["weclappOk"] is True
