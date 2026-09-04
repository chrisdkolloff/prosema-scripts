"""Transform UI: mode switch, PASS_1 field picker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.main import app
from app.models import TransformRow, TransformRun
from app.transform.ui import MSG_TRANSFORM_UNAVAILABLE
from core.article_write_fields import pass_1_fields
from tests.test_article_snapshots import PLAIN_USER, TENANT, _make_complete_snapshot


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


@patch("app.config.settings.assistant_enabled", True)
@patch("app.config.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_mode_switch_disabled_on_stale_and_non_current(db_session, user_client):
    older = _make_complete_snapshot(db_session)
    older.created_at = datetime.now(UTC) - timedelta(hours=30)
    newer = _make_complete_snapshot(db_session)
    newer.created_at = datetime.now(UTC)
    db_session.commit()

    stale = user_client.get(f"/artikel-uebersicht/{older.id}")
    assert stale.status_code == 200
    assert "Ändern" in stale.text
    assert "disabled" in stale.text
    assert "Neue Abfrage starten" in stale.text
    assert 'id="transform-spec-form"' not in stale.text

    current = user_client.get(f"/artikel-uebersicht/{newer.id}?modus=aendern")
    assert current.status_code == 200
    assert 'id="transform-spec-form"' in current.text
    assert 'id="snapshot-frage-form"' in current.text
    assert 'id="transform-manual-fallback"' in current.text
    assert "Wort ersetzen" in current.text or "replace_word" in current.text
    assert "Aktueller Filter:" in current.text


@patch("app.config.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_field_picker_is_pass_1_only(db_session, user_client):
    snapshot = _make_complete_snapshot(db_session)
    db_session.commit()
    response = user_client.get(f"/artikel-uebersicht/{snapshot.id}?modus=aendern")
    assert response.status_code == 200
    for field in pass_1_fields():
        assert field.snapshot_key in response.text
    assert 'value="Prosema-Artikelnummer"' not in response.text

    refused = user_client.post(
        f"/artikel-uebersicht/{snapshot.id}/transform/vorschau",
        data={
            "felder": "Prosema-Artikelnummer",
            "op_art": "replace_word",
            "op_suche": "a",
            "op_ersatz": "b",
            "artikelnummer": "010.020.0010",
        },
        follow_redirects=False,
    )
    assert refused.status_code == 400
    assert "darf in diesem Schritt nicht geändert werden" in refused.text


@patch("app.config.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_preview_post_refuses_non_current_snapshot(db_session, user_client):
    older = _make_complete_snapshot(db_session)
    older.created_at = datetime.now(UTC) - timedelta(hours=2)
    newer = _make_complete_snapshot(db_session)
    newer.created_at = datetime.now(UTC)
    db_session.commit()
    refused = user_client.post(
        f"/artikel-uebersicht/{older.id}/transform/vorschau",
        data={
            "felder": "Prosema-Artikelname",
            "op_art": "replace_word",
            "op_suche": "Profil",
            "op_ersatz": "Winkelprofil",
            "artikelnummer": "010.020.0010",
        },
        follow_redirects=False,
    )
    assert refused.status_code == 400
    assert MSG_TRANSFORM_UNAVAILABLE in refused.text


@patch("app.config.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_preview_post_refuses_stale_current_snapshot(db_session, user_client):
    snapshot = _make_complete_snapshot(db_session)
    snapshot.created_at = datetime.now(UTC) - timedelta(hours=30)
    db_session.commit()
    refused = user_client.post(
        f"/artikel-uebersicht/{snapshot.id}/transform/vorschau",
        data={
            "felder": "Prosema-Artikelname",
            "op_art": "replace_word",
            "op_suche": "Profil",
            "op_ersatz": "Winkelprofil",
            "artikelnummer": "010.020.0010",
        },
        follow_redirects=False,
    )
    assert refused.status_code == 400
    assert MSG_TRANSFORM_UNAVAILABLE in refused.text


def _stub_run(db_session, snapshot, *, apply_outcome=None):
    run = TransformRun(
        created_by_oid=PLAIN_USER["oid"],
        snapshot_id=snapshot.id,
        spec={
            "scope": {"article_numbers": ["010.020.0010"]},
            "fields": ["Prosema-Artikelname"],
            "operations": [{"op": "replace_word", "search": "a", "replace": "b"}],
        },
        status="previewed",
        candidate_count=1,
    )
    db_session.add(run)
    db_session.flush()
    row = TransformRow(
        run_id=run.id,
        article_number="010.020.0010",
        weclapp_id="1",
        field="Prosema-Artikelname",
        old_value="a",
        new_value="b",
        operations_fired=[],
        row_status="CHANGED",
        apply_outcome=apply_outcome,
    )
    db_session.add(row)
    db_session.commit()
    return run, row


@patch("app.config.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_confirm_post_refuses_stale_and_non_current_snapshot(db_session, user_client):
    older = _make_complete_snapshot(db_session)
    older.created_at = datetime.now(UTC) - timedelta(hours=2)
    newer = _make_complete_snapshot(db_session)
    newer.created_at = datetime.now(UTC)
    db_session.commit()
    run, row = _stub_run(db_session, older)
    refused = user_client.post(
        f"/transform/{run.id}/bestaetigen",
        data={"zeile": str(row.id)},
        follow_redirects=False,
    )
    assert refused.status_code == 400
    assert MSG_TRANSFORM_UNAVAILABLE in refused.text

    stale = _make_complete_snapshot(db_session)
    stale.created_at = datetime.now(UTC) - timedelta(hours=30)
    db_session.commit()
    run2, row2 = _stub_run(db_session, stale)
    aged = user_client.post(
        f"/transform/{run2.id}/bestaetigen",
        data={"zeile": str(row2.id)},
        follow_redirects=False,
    )
    assert aged.status_code == 400
    assert MSG_TRANSFORM_UNAVAILABLE in aged.text


@patch("app.config.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_reconcile_post_refuses_stale_and_non_current_snapshot(db_session, user_client):
    older = _make_complete_snapshot(db_session)
    older.created_at = datetime.now(UTC) - timedelta(hours=2)
    newer = _make_complete_snapshot(db_session)
    newer.created_at = datetime.now(UTC)
    db_session.commit()
    _, row = _stub_run(db_session, older, apply_outcome="UNKNOWN")
    refused = user_client.post(
        f"/transform/zeilen/{row.id}/abgleichen",
        follow_redirects=False,
    )
    assert refused.status_code == 400
    assert MSG_TRANSFORM_UNAVAILABLE in refused.text

    stale = _make_complete_snapshot(db_session)
    stale.created_at = datetime.now(UTC) - timedelta(hours=30)
    db_session.commit()
    _, row2 = _stub_run(db_session, stale, apply_outcome="UNKNOWN")
    aged = user_client.post(
        f"/transform/zeilen/{row2.id}/abgleichen",
        follow_redirects=False,
    )
    assert aged.status_code == 400
    assert MSG_TRANSFORM_UNAVAILABLE in aged.text


def test_format_spec_summary_de_matches_canonical_example():
    from app.transform.schemas import TransformSpec
    from app.transform.ui import format_spec_summary_de

    spec = TransformSpec.model_validate(
        {
            "scope": {
                "query_filter": {
                    "conditions": [
                        {
                            "column": "Untergruppe",
                            "operator": "eq",
                            "value": "Abschlussprofile Winkel",
                        }
                    ]
                }
            },
            "fields": [
                "Prosema-Artikelname",
                "Prosema-Langtext",
                "Kurzbeschreibung",
            ],
            "operations": [
                {
                    "op": "replace_literal",
                    "search": "Winkel-Abschlussprofil",
                    "replace": "Winkelprofil",
                },
                {
                    "op": "replace_literal",
                    "search": "Abschlussprofil",
                    "replace": "Winkelprofil",
                },
            ],
        }
    )
    text = format_spec_summary_de(spec)
    assert text.splitlines()[0].startswith(
        "In der Untergruppe «Abschlussprofile Winkel», Felder Name, Langtext, Kurzbeschreibung:"
    )
    assert "1. «Winkel-Abschlussprofil» → «Winkelprofil»" in text
    assert "2. «Abschlussprofil» → «Winkelprofil»" in text

