"""Assistant orchestration loop and assistant_queries audit."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.assistant.client import AssistantUnavailable, LLMResponse, ToolCall
from app.assistant.service import (
    MSG_DISABLED,
    MSG_DUPLICATE_CALL,
    MSG_NO_ANSWER,
    MSG_NO_SNAPSHOT,
    MSG_TURN_BUDGET,
    MSG_UNVERIFIED,
    TOOLS_BY_NAME,
    _parse_compatible_text,
    ask,
)
from app.assistant.tools import ToolResult
from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow, AssistantQuery

TENANT = "assistant-service-tenant"
USER = {
    "oid": "oid-assistant",
    "name": "Tester",
    "email": "tester@example.com",
    "roles": ["user"],
}
QUESTION = "Wie viele Artikel gibt es?"


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
        columns=[
            {"key": "Prosema Artikelnummer", "title": "Prosema Artikelnummer", "width": 120},
            {"key": "Einheit", "title": "Einheit", "width": 80},
            {"key": "Aktiv", "title": "Aktiv", "width": 60},
        ],
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
                data={
                    "Prosema Artikelnummer": number,
                    "Einheit": "Stk.",
                    "Aktiv": "Ja",
                },
                article_number=number,
                article_name=f"Artikel {position}",
                active=True,
                weclapp_id=f"id-{position}",
            )
        )
    db_session.flush()
    return snap


def _client(*responses: LLMResponse) -> MagicMock:
    mock = MagicMock()
    mock.complete.side_effect = list(responses)
    return mock


def _tool(name: str, arguments: dict | None = None) -> LLMResponse:
    return LLMResponse(
        text=None,
        tool_calls=[ToolCall(name=name, arguments=arguments or {})],
        prompt_tokens=11,
        completion_tokens=5,
        model="test-model",
    )


def _text(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=[],
        prompt_tokens=11,
        completion_tokens=7,
        model="test-model",
    )


def _json_text(payload: dict, *, fences: bool = False) -> LLMResponse:
    body = json.dumps(payload, ensure_ascii=False)
    if fences:
        body = f"```json\n{body}\n```"
    return LLMResponse(
        text=body,
        tool_calls=[],
        prompt_tokens=11,
        completion_tokens=7,
        model="test-model",
    )


def _audit(db_session, audit_id) -> AssistantQuery:
    row = db_session.get(AssistantQuery, audit_id)
    assert row is not None
    return row


def _wrap_handler(name: str) -> MagicMock:
    original = TOOLS_BY_NAME[name].handler
    return MagicMock(side_effect=original)


def _run(db_session, client, question=QUESTION, *, provider="azure", max_turns=4):
    with (
        patch("app.assistant.service.settings.assistant_enabled", True),
        patch("app.assistant.service.settings.assistant_provider", provider),
        patch("app.assistant.service.settings.assistant_max_tool_turns", max_turns),
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.assistant.service.get_client", return_value=client),
    ):
        return ask(db_session, USER, question)


def test_disabled_does_not_call_client(db_session, snapshot):
    client = MagicMock()
    with (
        patch("app.assistant.service.settings.assistant_enabled", False),
        patch("app.assistant.service.get_client", return_value=client) as get_client,
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
    ):
        result = ask(db_session, USER, QUESTION)
    assert result.outcome == "unavailable"
    assert result.hinweis_de == MSG_DISABLED
    get_client.assert_not_called()
    client.complete.assert_not_called()
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "unavailable"
    assert row.question_de == QUESTION


def test_no_snapshot_returns_unavailable(db_session):
    client = MagicMock()
    result = _run(db_session, client)
    assert result.outcome == "unavailable"
    assert result.hinweis_de == MSG_NO_SNAPSHOT
    client.complete.assert_not_called()
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "unavailable"
    assert row.snapshot_id is None
    assert row.error == MSG_NO_SNAPSHOT


def test_happy_path_zaehlen_then_answer(db_session, snapshot):
    client = _client(
        _tool("artikel_zaehlen", {"filters": {"conditions": []}}),
        _text("Es gibt 4 Artikel."),
    )
    result = _run(db_session, client)
    assert result.outcome == "answered"
    assert result.answer_de == "Es gibt 4 Artikel."
    assert result.rows == [{"anzahl": 4}]
    assert result.total_count == 4
    assert result.datenstand == snapshot.created_at
    row = _audit(db_session, result.audit_id)
    assert row.turns == 2
    assert row.outcome == "answered"
    assert row.snapshot_id == snapshot.id
    assert [call["name"] for call in row.tool_calls] == ["artikel_zaehlen"]
    assert client.complete.call_count == 2


def test_fabricated_number_is_unverified(db_session, snapshot, caplog):
    def fake_zaehlen(session, args):
        return ToolResult(
            rows=[{"anzahl": 42}],
            total_count=42,
            truncated=False,
            datenstand=snapshot.created_at,
            datenstand_hinweis_de="Datenstand: Beginn des Abzugs vom 01.01.2026, 12:00 Uhr.",
        )

    client = _client(
        _tool("artikel_zaehlen"),
        _text("Es gibt 999 Artikel"),
    )
    with (
        caplog.at_level(logging.WARNING, logger="app.assistant.service"),
        patch.object(TOOLS_BY_NAME["artikel_zaehlen"], "handler", fake_zaehlen),
    ):
        result = _run(db_session, client)
    assert result.outcome == "answered_unverified"
    assert result.answer_de is None
    assert result.rows == [{"anzahl": 42}]
    assert result.total_count == 42
    assert result.hinweis_de == MSG_UNVERIFIED
    assert "999" in caplog.text
    assert "Es gibt 999 Artikel" in caplog.text
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "answered_unverified"
    assert row.answer_de is None


def test_invalid_filter_is_fed_back_and_retried(db_session, snapshot):
    client = _client(
        _tool(
            "artikel_zaehlen",
            {
                "filters": {
                    "conditions": [
                        {"column": "foobar", "operator": "eq", "value": "rot"}
                    ]
                }
            },
        ),
        _tool("artikel_zaehlen", {"filters": {"conditions": []}}),
        _text("Es gibt 4 Artikel."),
    )
    result = _run(db_session, client)
    assert result.outcome == "answered"
    assert result.answer_de == "Es gibt 4 Artikel."
    assert client.complete.call_count == 3
    second_messages = client.complete.call_args_list[1].args[1]
    fed_back = json.dumps(second_messages, ensure_ascii=False)
    assert "Unbekannte Spalte" in fed_back
    assert "foobar" in fed_back
    row = _audit(db_session, result.audit_id)
    assert row.turns == 3
    assert row.tool_calls[0]["error"]
    assert "Unbekannte Spalte" in row.tool_calls[0]["error"]


def test_turn_budget_exhausted_without_answer(db_session, snapshot):
    client = _client(
        _tool("kein_tool"),
        _tool("auch_nicht"),
    )
    result = _run(db_session, client, max_turns=2)
    assert result.outcome == "error"
    assert result.hinweis_de == MSG_TURN_BUDGET
    assert result.answer_de is None
    assert result.rows == []
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "error"
    assert row.turns == 2
    assert row.error == MSG_TURN_BUDGET


def test_assistant_unavailable_writes_error_text(db_session, snapshot):
    client = MagicMock()
    client.complete.side_effect = AssistantUnavailable(
        "Das Sprachmodell ist derzeit nicht erreichbar."
    )
    result = _run(db_session, client)
    assert result.outcome == "unavailable"
    assert result.hinweis_de == "Das Sprachmodell ist derzeit nicht erreichbar."
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "unavailable"
    assert row.error == "Das Sprachmodell ist derzeit nicht erreichbar."


@pytest.mark.parametrize(
    "outcome",
    [
        "answered",
        "answered_unverified",
        "no_result",
        "no_answer",
        "invalid_input",
        "error",
        "unavailable",
    ],
)
def test_audit_row_written_for_every_outcome(db_session, snapshot, outcome):
    if outcome == "answered":
        result = _run(
            db_session,
            _client(_tool("artikel_zaehlen"), _text("Es gibt 4 Artikel.")),
        )
    elif outcome == "answered_unverified":
        result = _run(
            db_session,
            _client(_tool("artikel_zaehlen"), _text("Es gibt 999 Artikel")),
        )
    elif outcome == "no_result":
        result = _run(
            db_session,
            _client(
                _tool(
                    "artikel_suchen",
                    {
                        "filters": {
                            "conditions": [
                                {
                                    "column": "article_number",
                                    "operator": "eq",
                                    "value": "KEIN.TREFFER.0000",
                                }
                            ]
                        }
                    },
                ),
                _text("Keine Treffer."),
            ),
        )
    elif outcome == "no_answer":
        result = _run(
            db_session,
            _client(_tool("artikel_suchen"), _tool("artikel_suchen")),
            max_turns=2,
        )
    elif outcome == "invalid_input":
        result = _run(db_session, MagicMock(), question="  ")
    elif outcome == "error":
        result = _run(
            db_session,
            _client(_tool("kein_tool"), _tool("auch_nicht")),
            max_turns=2,
        )
    else:
        with (
            patch("app.assistant.service.settings.assistant_enabled", False),
            patch("app.assistant.service.get_client") as get_client,
        ):
            result = ask(db_session, USER, QUESTION)
            get_client.assert_not_called()
    assert result.outcome == outcome
    row = _audit(db_session, result.audit_id)
    assert row.outcome == outcome
    assert row.user_oid == USER["oid"]
    assert row.user_name == USER["name"]


def test_audit_write_failure_is_logged_and_result_returned(db_session, snapshot, caplog):
    client = _client(_tool("artikel_zaehlen"), _text("Es gibt 4 Artikel."))
    with (
        caplog.at_level(logging.ERROR, logger="app.assistant.service"),
        patch("app.assistant.service.settings.assistant_enabled", True),
        patch("app.assistant.service.settings.assistant_provider", "azure"),
        patch("app.assistant.service.settings.assistant_max_tool_turns", 4),
        patch("app.assistant.tools.settings.weclapp_tenant", TENANT),
        patch("app.assistant.catalog.settings.weclapp_tenant", TENANT),
        patch("app.assistant.service.get_client", return_value=client),
        patch.object(db_session, "commit", side_effect=RuntimeError("disk full")),
    ):
        result = ask(db_session, USER, QUESTION)
    assert result.outcome == "answered"
    assert result.answer_de == "Es gibt 4 Artikel."
    assert "assistant audit write failed" in caplog.text
    assert db_session.get(AssistantQuery, result.audit_id) is None


def test_openai_compatible_parses_fenced_json(db_session, snapshot):
    client = _client(
        _json_text({"tool": "artikel_zaehlen", "args": {}}, fences=True),
        _json_text({"answer": "Es gibt 4 Artikel."}),
    )
    result = _run(db_session, client, provider="openai_compatible")
    assert result.outcome == "answered"
    assert result.answer_de == "Es gibt 4 Artikel."
    assert result.rows == [{"anzahl": 4}]
    assert client.complete.call_count == 2
    _, _, tools = client.complete.call_args_list[0].args
    assert tools == []
    system = client.complete.call_args_list[0].args[0]
    assert '"tool"' in system
    row = _audit(db_session, result.audit_id)
    assert row.turns == 2


def test_openai_compatible_malformed_retries_then_errors(db_session, snapshot):
    client = _client(
        LLMResponse(text="dies ist kein json", tool_calls=[], model="test-model"),
        LLMResponse(text="{nope", tool_calls=[], model="test-model"),
    )
    result = _run(db_session, client, provider="openai_compatible")
    assert result.outcome == "error"
    assert result.hinweis_de == "Die Modellantwort war kein gültiges JSON."
    assert client.complete.call_count == 2
    retry_messages = client.complete.call_args_list[1].args[1]
    retry_text = json.dumps(retry_messages, ensure_ascii=False)
    assert "not valid JSON" in retry_text
    assert "ß" not in retry_text
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "error"
    assert row.turns == 2


def test_openai_compatible_trailing_text_parses_first_object(db_session, snapshot, caplog):
    blob = json.dumps({"tool": "artikel_zaehlen", "args": {}}, ensure_ascii=False)
    trailing = blob + " Extra data the model added after the object."
    client = _client(
        LLMResponse(text=trailing, tool_calls=[], model="test-model"),
        _json_text({"answer": "Es gibt 4 Artikel."}),
    )
    with caplog.at_level(logging.DEBUG, logger="app.assistant.service"):
        result = _run(db_session, client, provider="openai_compatible")
    assert result.outcome == "answered"
    assert result.rows == [{"anzahl": 4}]
    assert "discarded trailing JSON content" in caplog.text


def test_parse_compatible_text_trailing_and_malformed():
    answer, calls = _parse_compatible_text(
        '{"tool": "artikel_zaehlen", "args": {}} and then some prose'
    )
    assert answer is None
    assert calls[0].name == "artikel_zaehlen"
    with pytest.raises(ValueError):
        _parse_compatible_text("dies ist kein json")


def test_deleted_snapshot_nulls_audit_snapshot_id(db_session, snapshot):
    client = _client(_tool("artikel_zaehlen"), _text("Es gibt 4 Artikel."))
    result = _run(db_session, client)
    row = _audit(db_session, result.audit_id)
    assert row.snapshot_id == snapshot.id
    db_session.delete(snapshot)
    db_session.commit()
    db_session.expire(row)
    assert row.snapshot_id is None
    assert db_session.get(AssistantQuery, result.audit_id) is not None


def test_identical_repeated_call_is_not_executed_twice(db_session, snapshot, caplog):
    wrapped = _wrap_handler("artikel_suchen")
    client = _client(
        _tool("artikel_suchen"),
        _tool("artikel_suchen"),
        _text("Es gibt 4 Artikel."),
    )
    with (
        caplog.at_level(logging.INFO, logger="app.assistant.service"),
        patch.object(TOOLS_BY_NAME["artikel_suchen"], "handler", wrapped),
    ):
        result = _run(db_session, client)
    assert wrapped.call_count == 1
    assert result.outcome == "answered"
    assert result.total_count == 4
    second_observation = json.dumps(
        client.complete.call_args_list[2].args[1], ensure_ascii=False
    )
    assert MSG_DUPLICATE_CALL in second_observation
    assert "artikel_suchen" in caplog.text
    assert "repeat_count=2" in caplog.text


def test_third_identical_call_stops_with_no_answer(db_session, snapshot, caplog):
    wrapped = _wrap_handler("artikel_suchen")
    client = _client(
        _tool("artikel_suchen"),
        _tool("artikel_suchen"),
        _tool("artikel_suchen"),
        _text("sollte nicht erscheinen"),
    )
    with (
        caplog.at_level(logging.INFO, logger="app.assistant.service"),
        patch.object(TOOLS_BY_NAME["artikel_suchen"], "handler", wrapped),
    ):
        result = _run(db_session, client, max_turns=6)
    assert wrapped.call_count == 1
    assert client.complete.call_count == 3
    assert result.outcome == "no_answer"
    assert result.answer_de is None
    assert result.hinweis_de == MSG_NO_ANSWER
    assert len(result.rows) == 4
    assert result.total_count == 4
    assert "repeat_count=3" in caplog.text
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "no_answer"
    assert row.turns == 3
    assert row.total_count == 4
    assert [call["name"] for call in row.tool_calls] == ["artikel_suchen"] * 3


def test_budget_exhausted_after_suchen_is_no_answer(db_session, snapshot):
    wrapped = _wrap_handler("artikel_suchen")
    client = _client(
        _tool("artikel_suchen"),
        _tool("artikel_suchen"),
    )
    with patch.object(TOOLS_BY_NAME["artikel_suchen"], "handler", wrapped):
        result = _run(db_session, client, max_turns=2)
    assert wrapped.call_count == 1
    assert result.outcome == "no_answer"
    assert result.answer_de is None
    assert result.hinweis_de == MSG_NO_ANSWER
    assert len(result.rows) == 4
    assert result.total_count == 4
    assert result.columns
    row = _audit(db_session, result.audit_id)
    assert row.outcome == "no_answer"
    assert row.turns == 2
    assert row.total_count == 4
    assert row.error is None
    assert result.applied_article_numbers == [
        "881.010.0010",
        "881.010.0020",
        "881.010.0030",
        "881.010.0040",
    ]
    assert result.selection_truncated is False
    assert row.applied_article_numbers == result.applied_article_numbers
    assert row.selection_truncated is False
    assert row.applied_filter == {"conditions": []}


def test_same_args_different_key_order_are_duplicates(db_session, snapshot):
    wrapped = _wrap_handler("artikel_suchen")
    first = {
        "filters": {
            "conditions": [
                {"column": "Einheit", "operator": "eq", "value": "Stk."},
            ]
        }
    }
    second = {
        "filters": {
            "conditions": [
                {"value": "Stk.", "operator": "eq", "column": "Einheit"},
            ]
        }
    }
    client = _client(
        _tool("artikel_suchen", first),
        _tool("artikel_suchen", second),
        _text("Es gibt 4 Artikel."),
    )
    with patch.object(TOOLS_BY_NAME["artikel_suchen"], "handler", wrapped):
        result = _run(db_session, client)
    assert wrapped.call_count == 1
    assert result.outcome == "answered"
    fed_back = json.dumps(client.complete.call_args_list[2].args[1], ensure_ascii=False)
    assert MSG_DUPLICATE_CALL in fed_back


def test_same_tool_different_args_are_both_executed(db_session, snapshot):
    wrapped = _wrap_handler("artikel_suchen")
    client = _client(
        _tool(
            "artikel_suchen",
            {
                "filters": {
                    "conditions": [
                        {
                            "column": "article_number",
                            "operator": "eq",
                            "value": "881.010.0010",
                        }
                    ]
                }
            },
        ),
        _tool(
            "artikel_suchen",
            {
                "filters": {
                    "conditions": [
                        {
                            "column": "article_number",
                            "operator": "eq",
                            "value": "881.010.0020",
                        }
                    ]
                }
            },
        ),
        _text("Zwei verschiedene Suchen."),
    )
    with patch.object(TOOLS_BY_NAME["artikel_suchen"], "handler", wrapped):
        result = _run(db_session, client)
    assert wrapped.call_count == 2
    assert result.outcome == "answered"
    fed_back = json.dumps(client.complete.call_args_list[2].args[1], ensure_ascii=False)
    assert MSG_DUPLICATE_CALL not in fed_back


def test_hard_rules_forbid_column_to_column_comparison(db_session, snapshot):
    from app.assistant.prompts import (
        ANSWER_NOW_HINT,
        build_system_prompt,
        compatible_protocol_suffix,
    )

    prompt = build_system_prompt(db_session)
    assert "niemals mit einer anderen Spalte" in prompt
    assert "Verkaufspreis kleiner als Einkaufspreis" in prompt
    assert "erfinde keinen Wert" in prompt
    assert "höchstens einmal" in prompt
    assert "Nenne bei einer Trefferliste die Anzahl der Treffer" in prompt
    assert "höchstens zwei bis drei Beispiele" in prompt
    assert "nennst du" not in prompt
    assert "Schreibe in der ersten Person" in prompt
    assert "Ich habe 47 Artikel gefunden" in prompt
    assert "Ich kann «VPE 1» nicht numerisch vergleichen" in prompt
    assert "Sortierung, keinen Filter" in prompt
    assert "Preis grösser als 0" in prompt
    assert "Profile die mehr als 2 kg wiegen" in prompt
    assert "volltext" in prompt
    assert "Messing" in prompt
    assert "einzelne Spalte zu raten" in prompt
    assert ANSWER_NOW_HINT not in prompt
    assert ANSWER_NOW_HINT not in compatible_protocol_suffix([])


def test_question_numbers_are_allowed_in_refusal(db_session, snapshot):
    question = "Welche Artikel haben eine Lieferzeit über 10 Tage?"
    client = _client(
        _text(
            "«Lieferzeit» ist nicht im Katalog. "
            "Eine Filterung über 10 Tage ist nicht möglich."
        )
    )
    result = _run(db_session, client, question=question)
    assert result.outcome == "answered"
    assert result.answer_de is not None
    assert "10" in result.answer_de


def test_number_absent_from_question_and_tools_is_unverified(db_session, snapshot):
    question = "Welche Artikel haben eine Lieferzeit über 10 Tage?"
    client = _client(_text("Es gibt 88 Artikel ohne Lieferzeitangabe."))
    result = _run(db_session, client, question=question)
    assert result.outcome == "answered_unverified"
    assert result.answer_de is None
    assert result.hinweis_de == MSG_UNVERIFIED


def test_final_turn_azure_sends_tool_choice_none(db_session, snapshot):
    from app.assistant.prompts import FINAL_TURN_HINT

    client = _client(
        _tool("artikel_zaehlen"),
        _text("Es gibt 4 Artikel."),
    )
    result = _run(db_session, client, max_turns=2)
    assert result.outcome == "answered"
    first = client.complete.call_args_list[0]
    last = client.complete.call_args_list[1]
    assert "tool_choice" not in first.kwargs
    assert last.kwargs.get("tool_choice") == "none"
    last_messages = last.args[1]
    assert any(FINAL_TURN_HINT in str(msg.get("content") or "") for msg in last_messages)


def test_compatible_tool_result_contains_answer_now_hint(db_session, snapshot):
    from app.assistant.prompts import ANSWER_NOW_HINT

    client = _client(
        _json_text({"tool": "artikel_zaehlen", "args": {}}),
        _json_text({"answer": "Es gibt 4 Artikel."}),
    )
    result = _run(db_session, client, provider="openai_compatible")
    assert result.outcome == "answered"
    second_messages = client.complete.call_args_list[1].args[1]
    contents = [str(msg.get("content") or "") for msg in second_messages]
    assert any(ANSWER_NOW_HINT in text for text in contents)


def test_answered_stores_validated_filter_not_raw_alias(db_session, snapshot):
    client = _client(
        _tool(
            "artikel_suchen",
            {
                "filters": {
                    "conditions": [
                        {
                            "column": "Prosema Artikelnummer",
                            "operator": "eq",
                            "value": "881.010.0020",
                        }
                    ]
                }
            },
        ),
        _text("Ein Artikel."),
    )
    result = _run(db_session, client)
    assert result.outcome == "answered"
    assert result.applied_article_numbers == ["881.010.0020"]
    row = _audit(db_session, result.audit_id)
    assert row.applied_filter == {
        "conditions": [
            {"column": "article_number", "operator": "eq", "value": "881.010.0020"}
        ]
    }


def test_selection_above_cap_stores_null_and_truncated(db_session, snapshot):
    client = _client(
        _tool("artikel_zaehlen", {"filters": {"conditions": []}}),
        _text("Es gibt 4 Artikel."),
    )
    with patch("app.assistant.service.MAX_SELECTION_ROWS", 2):
        result = _run(db_session, client)
    assert result.outcome == "answered"
    assert result.applied_article_numbers is None
    assert result.selection_truncated is True
    row = _audit(db_session, result.audit_id)
    assert row.applied_article_numbers is None
    assert row.selection_truncated is True
    assert row.applied_filter == {"conditions": []}


def test_error_outcome_does_not_store_selection(db_session, snapshot):
    client = _client(_tool("kein_tool"), _tool("auch_nicht"))
    result = _run(db_session, client, max_turns=2)
    assert result.outcome == "error"
    assert result.applied_article_numbers is None
    assert result.selection_truncated is False
    row = _audit(db_session, result.audit_id)
    assert row.applied_article_numbers is None
    assert row.applied_filter is None
    assert row.selection_truncated is False
