"""Transform preview: live GET only."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.jobs import HANDLERS
from app.models import ArticleSnapshot, ArticleSnapshotRow, TransformRow
from app.transform.preview import TransformAuthAbort, run_preview
from app.transform.schemas import TransformSpec
from scripts.weclapp.client import WeclappError
from tests.test_article_write import FakeWeclappClient, _article


@pytest.fixture
def db_session():
    from sqlalchemy.orm import Session

    from app.db import engine

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


def _complete_snapshot(db, *, number="999.999.001", weclapp_id="353023", name="Alte Folie"):
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="n",
        weclapp_tenant="prosema",
        row_count=1,
        columns=[],
    )
    db.add(snap)
    db.flush()
    db.add(
        ArticleSnapshotRow(
            snapshot_id=snap.id,
            position=0,
            data={"Prosema-Artikelname": name},
            article_number=number,
            article_name=name,
            weclapp_id=weclapp_id,
        )
    )
    db.flush()
    return snap


def _spec():
    return TransformSpec.model_validate(
        {
            "scope": {"article_numbers": ["999.999.001"]},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {
                    "op": "replace_literal",
                    "search": "Alte Folie",
                    "replace": "Neue Folie",
                }
            ],
        }
    )


def _run(db, snap, spec, client):
    from app.models import TransformRun

    run = TransformRun(
        created_by_oid="oid",
        snapshot_id=snap.id,
        spec=spec.model_dump(mode="json"),
        status="previewing",
    )
    db.add(run)
    db.flush()
    return run, run_preview(db, run, oid="oid", client=client)


def test_preview_changed_persists_live_old_and_never_puts(db_session):
    snap = _complete_snapshot(db_session)
    client = FakeWeclappClient(_article())
    run, result = _run(db_session, snap, _spec(), client)
    assert client.put_calls == []
    assert result["changed_rows"] == 1
    row = db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id)).one()
    assert row.row_status == "CHANGED"
    assert row.old_value == "Alte Folie"
    assert row.new_value == "Neue Folie"
    assert row.version_at_preview == "10"
    assert run.status == "previewed"


def test_preview_unchanged_skips_live_get(db_session):
    snap = _complete_snapshot(db_session, name="Keine Treffer")
    client = FakeWeclappClient(_article(name="Keine Treffer"))
    spec = TransformSpec.model_validate(
        {
            "scope": {"article_numbers": ["999.999.001"]},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {"op": "replace_literal", "search": "zzz", "replace": "yyy"}
            ],
        }
    )
    run, result = _run(db_session, snap, spec, client)
    assert result["candidate_count"] == 0
    assert result["changed_rows"] == 0
    assert list(db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))) == []
    assert [c for c in client.get_calls if c.startswith("/article/")] == []
    assert client.put_calls == []


def test_preview_gone(db_session):
    snap = _complete_snapshot(db_session)
    client = FakeWeclappClient(
        _article(), get_error=WeclappError("missing", status_code=404)
    )
    run, _result = _run(db_session, snap, _spec(), client)
    row = db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id)).one()
    assert row.row_status == "GONE"
    assert client.put_calls == []


def test_preview_auth_aborts(db_session):
    snap = _complete_snapshot(db_session)
    client = FakeWeclappClient(
        _article(), get_error=WeclappError("nope", status_code=401)
    )
    from app.models import TransformRun

    run = TransformRun(
        created_by_oid="oid",
        snapshot_id=snap.id,
        spec=_spec().model_dump(mode="json"),
        status="previewing",
    )
    db_session.add(run)
    db_session.flush()
    with pytest.raises(TransformAuthAbort) as exc:
        run_preview(db_session, run, oid="oid", client=client)
    from app.weclapp import MSG_INVALID

    assert str(exc.value) == MSG_INVALID
    assert client.put_calls == []


def test_preview_job_registered():
    assert "article_transform_preview" in HANDLERS


def test_scope_accepts_more_than_former_ceiling(db_session):
    from app.transform.scope import resolve_scope

    snap = _complete_snapshot(db_session)
    numbers = [f"999.999.{i:04d}" for i in range(1001)]
    spec = TransformSpec.model_validate(
        {
            "scope": {"article_numbers": numbers},
            "fields": ["Prosema-Artikelname"],
            "operations": [{"op": "remove_literal", "search": "x"}],
        }
    )
    candidates = resolve_scope(db_session, snap, spec)
    assert len(candidates) == 1001


def test_short_list_page_records_gone_without_per_id_get(db_session):
    from tests.test_transform_apply import CatalogFake, _article, _preview, _snapshot, _spec

    present = _article("1", "999.999.001", "Alte Folie")
    missing = _article("2", "999.999.002", "Alte Folie")
    snap = _snapshot(db_session, [present, missing])
    client = CatalogFake([present, missing])
    client.omit_from_list.add("2")
    run = _preview(
        db_session,
        snap,
        _spec(["999.999.001", "999.999.002"]),
        client,
    )
    rows = {
        r.article_number: r
        for r in db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    }
    assert rows["999.999.001"].row_status == "CHANGED"
    assert rows["999.999.002"].row_status == "GONE"
    assert "/article/id/2" not in client.get_calls


def test_preview_resume_skips_candidates_that_already_have_rows(db_session, monkeypatch):
    from app.article_write import live_field_value as real_live
    from app.transform import preview as preview_mod
    from tests.test_transform_apply import CatalogFake, _article, _snapshot, _spec

    arts = [
        _article("1", "999.999.001", "Alte Folie"),
        _article("2", "999.999.002", "Alte Folie"),
    ]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    spec = _spec([a["articleNumber"] for a in arts])
    from app.models import TransformRun

    run = TransformRun(
        created_by_oid="oid",
        snapshot_id=snap.id,
        spec=spec.model_dump(mode="json"),
        status="previewing",
    )
    db_session.add(run)
    db_session.flush()

    seen = {"n": 0}

    def boom(article, snapshot_key, resolver):
        seen["n"] += 1
        if seen["n"] > 1:
            raise RuntimeError("interrupt mid-batch")
        return real_live(article, snapshot_key, resolver)

    monkeypatch.setattr(preview_mod, "live_field_value", boom)
    with pytest.raises(RuntimeError, match="interrupt mid-batch"):
        run_preview(db_session, run, oid="oid", client=client)
    first = list(
        db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    )
    assert len(first) == 1
    assert first[0].article_number == "999.999.001"
    monkeypatch.setattr(preview_mod, "live_field_value", real_live)
    run_preview(db_session, run, oid="oid", client=client)
    numbers = [
        r.article_number
        for r in db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    ]
    assert sorted(numbers) == ["999.999.001", "999.999.002"]
    assert numbers.count("999.999.001") == 1

