"""transform_vorschlagen proposes a spec; it does not preview or write."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.schemas import TransformVorschlagenArgs
from app.assistant.service import TOOL_SPECS, WRITE_TOOL_SPECS, ask
from app.assistant.tools import transform_vorschlagen
from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow
from app.transform.schemas import MSG_AMP, MSG_NOT_PASS_1, MSG_STAR_SEARCH
from tests.test_assistant_service import QUESTION, TENANT, USER, _client, _text


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
def snapshot(db_session):
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
        row_count=4,
        columns=[],
        non_conforming_number_count=0,
        created_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()
    for position, number in enumerate(
        ("881.010.0010", "881.010.0020", "881.010.0030", "881.010.0040")
    ):
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snap.id,
                position=position,
                data={"Prosema Artikelnummer": number, "Aktiv": "Ja"},
                article_number=number,
                article_name=f"Artikel {position}",
                active=True,
                weclapp_id=f"id-{position}",
            )
        )
    db_session.flush()
    return snap


def test_read_tools_unchanged():
    names = [spec.name for spec in TOOL_SPECS]
    assert names == [
        "artikel_suchen",
        "artikel_zaehlen",
        "artikel_details",
        "gruppen_auflisten",
        "einheiten_auflisten",
        "datenstand",
    ]
    assert "transform_vorschlagen" not in names
    assert {spec.name for spec in WRITE_TOOL_SPECS} >= {
        "transform_vorschlagen",
        "gruppen_zuordnen",
    }


def test_handler_source_cannot_reach_preview_or_write():
    source = inspect.getsource(transform_vorschlagen)
    for forbidden in (
        "start_transform_preview",
        "start_transform_apply",
        "update_article",
        "approve_chunk",
        "reconcile_unknown_row",
    ):
        assert forbidden not in source


def test_ampersand_is_tool_result_not_exception(db_session, snapshot):
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {"conditions": []},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {"op": "replace_literal", "search": "Rand & Ecke", "replace": "Randecke"}
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.transform.preview.start_transform_preview") as preview,
    ):
        result = transform_vorschlagen(db_session, args)
    assert MSG_AMP in result.hinweis_de
    assert result.rows == []
    preview.assert_not_called()


def test_star_search_refused_at_tool_boundary(db_session, snapshot):
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {
                "conditions": [
                    {
                        "column": "article_number",
                        "operator": "eq",
                        "value": "881.010.0010",
                    }
                ]
            },
            "fields": ["Prosema-Langtext"],
            "operations": [
                {
                    "op": "replace_literal",
                    "search": "*",
                    "replace": "TEST BESCHREIBUNG",
                }
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.transform.preview.start_transform_preview") as preview,
    ):
        result = transform_vorschlagen(db_session, args)
    assert MSG_STAR_SEARCH in result.hinweis_de
    assert result.rows == []
    preview.assert_not_called()


def test_forbidden_untergruppe_refused_at_tool_boundary(db_session, snapshot):
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {"conditions": []},
            "fields": ["Untergruppe"],
            "operations": [
                {
                    "op": "replace_literal",
                    "search": "Abschlussprofile Winkel",
                    "replace": "Winkelprofile",
                }
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.transform.preview.start_transform_preview") as preview,
    ):
        result = transform_vorschlagen(db_session, args)
    assert MSG_NOT_PASS_1.format(field="Untergruppe") in result.hinweis_de
    assert result.rows == []
    preview.assert_not_called()


def test_empty_replace_literal_proposes_spec(db_session, snapshot):
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {"conditions": []},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {"op": "replace_literal", "search": "[", "replace": ""}
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
    ):
        result = transform_vorschlagen(db_session, args)
    assert result.rows
    assert result.rows[0]["spec"]["operations"][0]["replace"] == ""


def test_non_idempotent_replace_literal_warning_reaches_hinweis(db_session, snapshot):
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {"conditions": []},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {
                    "op": "replace_literal",
                    "search": "Artikel",
                    "replace": "xArtikel",
                }
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
    ):
        result = transform_vorschlagen(db_session, args)
    assert result.rows
    warnings = result.rows[0]["spec"]["idempotency_warnings"]
    assert warnings
    assert "nicht idempotent" in warnings[0]
    assert "nicht idempotent" in result.hinweis_de


def test_valid_spec_does_not_call_preview(db_session, snapshot):
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {"conditions": []},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {"op": "replace_word", "search": "weiss", "replace": "Weiss"}
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.transform.preview.start_transform_preview") as preview,
    ):
        result = transform_vorschlagen(db_session, args)
    assert result.rows
    assert result.rows[0]["spec"]["operations"][0]["search"] == "weiss"
    preview.assert_not_called()


def test_read_ask_does_not_advertise_write_tool(db_session, snapshot):
    client = _client(_text("Es gibt 4 Artikel."))
    with (
        patch("app.assistant.service.settings.assistant_enabled", True),
        patch("app.assistant.service.settings.assistant_provider", "azure"),
        patch("app.assistant.service.settings.assistant_max_tool_turns", 4),
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.assistant.service.get_client", return_value=client),
    ):
        ask(db_session, USER, QUESTION)
    schemas = client.complete.call_args.args[2]
    names = [item["function"]["name"] for item in schemas]
    assert "transform_vorschlagen" not in names
    assert len(names) == 6


def test_write_ask_advertises_vorschlagen(db_session, snapshot):
    client = _client(_text("Ich schlage nichts vor, der Auftrag ist unklar."))
    with (
        patch("app.assistant.service.settings.assistant_enabled", True),
        patch("app.assistant.service.settings.assistant_provider", "azure"),
        patch("app.assistant.service.settings.assistant_max_tool_turns", 4),
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.assistant.service.get_client", return_value=client),
    ):
        ask(db_session, USER, QUESTION, write_mode=True)
    schemas = client.complete.call_args.args[2]
    names = [item["function"]["name"] for item in schemas]
    assert names[-1] == "gruppen_zuordnen"
    assert "transform_vorschlagen" in names
    assert len(names) == 8
    system = client.complete.call_args.args[0]
    assert "verbinder" in system
    assert "Winkel-Winkelprofil" in system
    assert "mm" in system
    assert '"answer"' in system
    assert "150  mm" in system
    assert "kein Platzhalter" in system


def test_article_name_alias_maps_to_pass_1_snapshot_key(db_session, snapshot):
    from core.article_payload import ARTICLE_NAME_FIELD

    from app.assistant.tools import snapshot_key_for_transform_field

    assert snapshot_key_for_transform_field("article_name") == ARTICLE_NAME_FIELD
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {"conditions": []},
            "fields": ["article_name"],
            "operations": [
                {"op": "replace_word", "search": "weiss", "replace": "Weiss"}
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
    ):
        result = transform_vorschlagen(db_session, args)
    assert result.rows
    assert result.rows[0]["spec"]["fields"] == [ARTICLE_NAME_FIELD]


def test_pass_1_fields_with_assistant_name_mismatch():
    from app.assistant.catalog import get_column
    from core.article_write_fields import pass_1_fields

    mismatches = []
    for field in pass_1_fields():
        col = get_column(field.snapshot_key)
        if col is None:
            continue
        if col.name != field.snapshot_key:
            mismatches.append((field.snapshot_key, col.name))
    assert mismatches == [("Prosema-Artikelname", "article_name")]


def test_mm_insertion_refused_when_spaced_form_already_present(db_session, snapshot):
    row = db_session.scalars(
        select(ArticleSnapshotRow).where(ArticleSnapshotRow.snapshot_id == snapshot.id)
    ).first()
    assert row is not None
    row.article_name = "Winkelprofil 150 mm"
    db_session.flush()
    args = TransformVorschlagenArgs.model_validate(
        {
            "filters": {"conditions": []},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {"op": "replace_literal", "search": "mm", "replace": " mm"}
            ],
        }
    )
    with (
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
    ):
        result = transform_vorschlagen(db_session, args)
    assert result.rows == []
    assert "1 bestehender Wert enthält bereits « mm»" in result.hinweis_de
    assert "«Winkelprofil 150 mm»" in result.hinweis_de
