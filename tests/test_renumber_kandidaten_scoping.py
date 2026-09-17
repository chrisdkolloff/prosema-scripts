"""Unit tests for renumber_kandidaten group-pair scoping."""

from __future__ import annotations

import unittest.mock as mock

import pytest
from sqlalchemy.orm import Session

from app.article_renumber import list_mismatch_candidates
from app.article_renumber_eligibility import EligibilityResult
from app.assistant.schemas import RenumberKandidatenArgs
from app.assistant.tools import renumber_kandidaten
from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow

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


def _snapshot(session: Session) -> ArticleSnapshot:
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
    )
    session.add(snap)
    session.flush()
    return snap


def test_renumber_kandidaten_args_normalize_gruppe_pairs():
    args = RenumberKandidatenArgs(
        scope="all_mismatches",
        quellgruppe="020.120.0010",
        zielgruppe="040.050",
    )
    assert args.quellgruppe == "020.120"
    assert args.zielgruppe == "040.050"


def test_renumber_kandidaten_args_reject_invalid_gruppe():
    with pytest.raises(ValueError):
        RenumberKandidatenArgs(scope="all_mismatches", quellgruppe="abc")


def test_list_mismatch_candidates_applies_gruppe_filters(db_session):
    snapshot = _snapshot(db_session)
    rows = [
        ("020.120.0010", "a1"),
        ("020.120.0020", "a2"),
        ("020.130.0010", "b1"),
    ]
    for index, (number, wc_id) in enumerate(rows):
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snapshot.id,
                position=index,
                data={"article_number": number},
                article_number=number,
                weclapp_id=wc_id,
            )
        )
    db_session.commit()

    def fake_prefetch(db, client):
        from app.article_renumber_eligibility import RenumberPrefetch

        ctx = RenumberPrefetch()
        ctx.category_id_to_pair = {
            "cat-a": ("040", "050"),
            "cat-b": ("020", "130"),
        }
        return ctx

    articles = {
        "a1": {"id": "a1", "articleNumber": "020.120.0010", "articleCategoryId": "cat-a"},
        "a2": {"id": "a2", "articleNumber": "020.120.0020", "articleCategoryId": "cat-a"},
        "b1": {"id": "b1", "articleNumber": "020.130.0010", "articleCategoryId": "cat-a"},
    }

    def fake_fetch(client, candidates):
        from app.transform.live_fetch import LiveFetchResult

        result = LiveFetchResult()
        for c in candidates:
            if c.weclapp_id in articles:
                result.articles[c.weclapp_id] = articles[c.weclapp_id]
        return result

    ok = EligibilityResult(ok=True, reason_code=None, checks={"no_mismatch": True})
    with (
        mock.patch("app.article_renumber.prefetch_renumber_context", fake_prefetch),
        mock.patch("app.article_renumber.fetch_live_articles", fake_fetch),
        mock.patch("app.article_renumber.evaluate_eligibility", return_value=ok),
    ):
        client = mock.Mock()
        filtered = list_mismatch_candidates(
            db_session,
            client,
            snapshot=snapshot,
            quellgruppe="020.120",
            zielgruppe="040.050",
        )
        all_mm = list_mismatch_candidates(db_session, client, snapshot=snapshot)

    assert len(all_mm) == 3
    assert len(filtered) == 2
    assert {m["article_number"] for m in filtered} == {"020.120.0010", "020.120.0020"}


def test_renumber_kandidaten_returns_all_filtered_rows(db_session):
    snapshot = _snapshot(db_session)
    for index in range(20):
        number = f"020.120.{index:04d}"
        db_session.add(
            ArticleSnapshotRow(
                snapshot_id=snapshot.id,
                position=index,
                data={"article_number": number},
                article_number=number,
                weclapp_id=f"id-{index}",
            )
        )
    db_session.commit()

    items = [
        {
            "weclapp_id": f"id-{index}",
            "article_number": f"020.120.{index:04d}",
            "number_pair": "020.120",
            "category_pair": "040.050",
            "eligibility": EligibilityResult(ok=False, reason_code="x", checks={}),
        }
        for index in range(20)
    ]

    with (
        mock.patch("app.assistant.tools._weclapp_client_for_assistant", return_value=mock.Mock()),
        mock.patch("app.assistant.tools.resolve_current_snapshot", return_value=snapshot),
        mock.patch("app.article_renumber.list_mismatch_candidates", return_value=items),
    ):
        result = renumber_kandidaten(
            db_session,
            RenumberKandidatenArgs(
                scope="all_mismatches",
                quellgruppe="020.120",
                zielgruppe="040.050",
            ),
        )

    assert result.total_count == 20
    assert len(result.rows) == 20
    assert result.truncated is False
