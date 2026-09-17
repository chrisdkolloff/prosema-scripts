"""Unit tests for scoped renumber_vorschlagen (batch ArticleRenumberSpec)."""

from __future__ import annotations

from unittest import mock

import pytest
from sqlalchemy.orm import Session

from app.article_renumber_eligibility import EligibilityResult
from app.assistant.schemas import RenumberVorschlagenArgs
from app.assistant.tools import renumber_vorschlagen
from app.db import engine
from tests.test_renumber_kandidaten_scoping import _snapshot


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


def test_renumber_vorschlagen_args_reject_empty_target():
    try:
        RenumberVorschlagenArgs.model_validate({})
    except ValueError as exc:
        assert "article_identifier" in str(exc) or "quellgruppe" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_renumber_vorschlagen_scoped_builds_spec(db_session):
    snapshot = _snapshot(db_session)
    ok = EligibilityResult(ok=True, reason_code=None, checks={})
    blocked = EligibilityResult(ok=False, reason_code="x", checks={})
    items = [
        {
            "weclapp_id": f"id-{index}",
            "article_number": f"020.120.{index:04d}",
            "number_pair": "020.120",
            "category_pair": "040.050",
            "eligibility": ok if index < 20 else blocked,
        }
        for index in range(21)
    ]

    with (
        mock.patch("app.assistant.tools._weclapp_client_for_assistant", return_value=mock.Mock()),
        mock.patch("app.assistant.tools.resolve_current_snapshot", return_value=snapshot),
        mock.patch("app.assistant.catalog.assistant_actor", return_value={"roles": ["admin"]}),
        mock.patch("app.article_renumber.list_mismatch_candidates", return_value=items),
    ):
        result = renumber_vorschlagen(
            db_session,
            RenumberVorschlagenArgs(quellgruppe="020.120", zielgruppe="040.050"),
        )

    assert result.total_count == 20
    assert result.rows
    spec = result.rows[0]["spec"]
    assert spec["kind"] == "article_renumber"
    assert len(spec["scope"]["article_numbers"]) == 20
    assert "Vorschau" in (result.hinweis_de or "")


def test_renumber_vorschlagen_scoped_refuses_when_none_eligible(db_session):
    snapshot = _snapshot(db_session)
    blocked = EligibilityResult(ok=False, reason_code="x", checks={})
    items = [
        {
            "weclapp_id": "a1",
            "article_number": "020.120.0010",
            "number_pair": "020.120",
            "category_pair": "040.050",
            "eligibility": blocked,
        }
    ]

    with (
        mock.patch("app.assistant.tools._weclapp_client_for_assistant", return_value=mock.Mock()),
        mock.patch("app.assistant.tools.resolve_current_snapshot", return_value=snapshot),
        mock.patch("app.assistant.catalog.assistant_actor", return_value={"roles": ["admin"]}),
        mock.patch("app.article_renumber.list_mismatch_candidates", return_value=items),
    ):
        result = renumber_vorschlagen(
            db_session,
            RenumberVorschlagenArgs(quellgruppe="020.120"),
        )

    assert result.total_count == 1
    assert not any(isinstance(row, dict) and row.get("spec") for row in result.rows)
    assert "0 derzeit umnummerierbar" in (result.hinweis_de or "")
