"""Transform apply: faked weclapp, per-row commits, AUTH abort, re-run."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.jobs import HANDLERS
from app.models import (
    ArticleSnapshot,
    ArticleSnapshotRow,
    AuditLog,
    TransformChunk,
    TransformRow,
    TransformRun,
)
from app.transform.apply import (
    CHUNK_SIZE,
    apply_chunk,
    approve_chunk,
    preview_run_for_conflicts,
)
from app.transform.preview import TransformAuthAbort, run_preview
from app.transform.schemas import TransformSpec
from app.transform.summary import chunk_result_summary, preview_summary
from app.weclapp import MSG_INVALID
from scripts.weclapp.client import WeclappError
from tests.test_article_write import PASS1_DEFS, _ids_from_in_param


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


class CatalogFake:
    def __init__(self, articles: list[dict[str, Any]]) -> None:
        self.by_id = {str(a["id"]): copy.deepcopy(a) for a in articles}
        self.definitions = list(PASS1_DEFS)
        self.get_errors: dict[str, WeclappError] = {}
        self.put_errors: dict[str, WeclappError] = {}
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []
        self.omit_from_list: set[str] = set()

    def get(self, path: str, *, params=None) -> Any:
        self.get_calls.append(path)
        if "/article/id/" in path:
            article_id = path.rsplit("/", 1)[-1]
            if article_id in self.get_errors:
                raise self.get_errors[article_id]
            if article_id not in self.by_id:
                raise WeclappError("missing", status_code=404)
            return copy.deepcopy(self.by_id[article_id])
        if path.rstrip("/") == "/article" or path == "/article":
            wanted = _ids_from_in_param((params or {}).get("id-in"))
            like = str((params or {}).get("articleNumber-like") or "")
            rows = []
            for article in self.by_id.values():
                article_id = str(article["id"])
                number = str(article.get("articleNumber") or "")
                if wanted and article_id not in wanted:
                    continue
                if like.endswith("%") and not number.startswith(like[:-1]):
                    continue
                if article_id in self.omit_from_list:
                    continue
                rows.append(copy.deepcopy(article))
            return {"result": rows}
        raise WeclappError("missing", status_code=404)

    def iter_pages(self, entity: str, *, params=None, page_size=None):
        if entity == "customAttributeDefinition":
            yield from self.definitions
            return
        if entity == "article":
            payload = self.get("/article", params=dict(params or {}))
            yield from payload.get("result") or []
            return
        yield from self.definitions

    def put(self, path: str, *, params=None, json=None) -> Any:
        self.put_calls.append({"path": path, "params": params, "json": json})
        article_id = path.rsplit("/", 1)[-1]
        live = self.by_id[article_id]
        body = dict(json or {})
        if str(body.get("version")) != str(live.get("version")):
            raise WeclappError("stale", status_code=409, detail={"error": "optimisticLock"})
        if article_id in self.put_errors:
            raise self.put_errors[article_id]
        version_after = str(int(str(live["version"])) + 1)
        updated = copy.deepcopy(live)
        for key, value in body.items():
            if key == "customAttributes":
                continue
            updated[key] = value
        updated["version"] = version_after
        self.by_id[article_id] = updated
        return copy.deepcopy(updated)


def _article(article_id: str, number: str, name: str, version: str = "10") -> dict[str, Any]:
    return {
        "id": article_id,
        "articleNumber": number,
        "version": version,
        "name": name,
        "longText": f"<p>{name}</p>",
        "shortDescription1": name,
        "matchCode": "X",
        "customAttributes": [],
    }


def _snapshot(db: Session, articles: list[dict[str, Any]]) -> ArticleSnapshot:
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="n",
        weclapp_tenant="prosema",
        row_count=len(articles),
        columns=[],
    )
    db.add(snap)
    db.flush()
    for i, art in enumerate(articles):
        db.add(
            ArticleSnapshotRow(
                snapshot_id=snap.id,
                position=i,
                data={"Prosema-Artikelname": art["name"]},
                article_number=art["articleNumber"],
                article_name=art["name"],
                weclapp_id=art["id"],
            )
        )
    db.flush()
    return snap


def _spec(numbers: list[str], search: str = "Alte Folie", replace: str = "Neue Folie"):
    return TransformSpec.model_validate(
        {
            "scope": {"article_numbers": numbers},
            "fields": ["Prosema-Artikelname"],
            "operations": [{"op": "replace_literal", "search": search, "replace": replace}],
        }
    )


def _preview(db, snap, spec, client) -> TransformRun:
    run = TransformRun(
        created_by_oid="oid",
        snapshot_id=snap.id,
        spec=spec.model_dump(mode="json"),
        status="previewing",
        case_variants=[],
        word_positions={},
    )
    db.add(run)
    db.flush()
    run_preview(db, run, oid="oid", client=client)
    db.commit()
    db.refresh(run)
    return run


def test_preview_word_position_standalone_vs_compound(db_session):
    a = _article("1", "999.999.001", "Abschlussprofil Aluminium")
    b = _article("2", "999.999.002", "Winkel-Abschlussprofil Aluminium")
    snap = _snapshot(db_session, [a, b])
    client = CatalogFake([a, b])
    spec = TransformSpec.model_validate(
        {
            "scope": {"article_numbers": ["999.999.001", "999.999.002"]},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {
                    "op": "replace_literal",
                    "search": "Abschlussprofil",
                    "replace": "Winkelprofil",
                }
            ],
        }
    )
    run = _preview(db_session, snap, spec, client)
    by_num = {r.article_number: r for r in run.rows}
    assert by_num["999.999.001"].inside_compound is False
    assert by_num["999.999.002"].inside_compound is True
    assert run.word_positions["standalone"] == 1
    assert run.word_positions["embedded"] == 1
    text = preview_summary(run)
    assert "1 Änderungen an eigenständigen Vorkommen" in text
    assert "1 Änderungen innerhalb eines zusammengesetzten Wortes" in text
    assert client.put_calls == []


def test_approve_chunk_persists_row_ids(db_session):
    arts = [
        _article("1", "999.999.001", "Alte Folie"),
        _article("2", "999.999.002", "Alte Folie"),
    ]
    snap = _snapshot(db_session, arts)
    run = _preview(db_session, snap, _spec([a["articleNumber"] for a in arts]), CatalogFake(arts))
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="approver-1")
    db_session.commit()
    again = db_session.get(TransformChunk, chunk.id)
    assert again is not None
    assert again.approved_by_oid == "approver-1"
    assert again.chunk_index == 0
    assert len(again.row_ids) == 2
    assert CHUNK_SIZE == 200


def test_clean_chunk_mixed_outcomes(db_session):
    updated = _article("1", "999.999.001", "Alte Folie")
    unchanged = _article("2", "999.999.002", "Alte Folie")
    conflict = _article("3", "999.999.003", "Alte Folie", version="10")
    rejected = _article("4", "999.999.004", "Alte Folie")
    gone = _article("5", "999.999.005", "Alte Folie")
    arts = [updated, unchanged, conflict, rejected, gone]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    run = _preview(
        db_session,
        snap,
        _spec([a["articleNumber"] for a in arts]),
        client,
    )
    # Live already has the target for one row; version bumped for another.
    client.by_id["2"]["name"] = "Neue Folie"
    client.by_id["3"]["version"] = "99"
    client.put_errors["4"] = WeclappError(
        "bad", status_code=400, detail={"error": "validation"}
    )
    client.get_errors["5"] = WeclappError("missing", status_code=404)

    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")
    apply_chunk(db_session, chunk, oid="oid-writer", actor_name="Writer", client=client)
    db_session.expire_all()
    rows = {
        r.article_number: r
        for r in db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    }
    assert rows["999.999.001"].apply_outcome == "UPDATED"
    assert rows["999.999.002"].apply_outcome == "UNCHANGED"
    assert rows["999.999.003"].apply_outcome == "CONFLICT"
    assert rows["999.999.003"].apply_version_seen == "99"
    assert rows["999.999.004"].apply_outcome == "REJECTED"
    assert rows["999.999.004"].apply_detail == {"error": "validation"}
    assert rows["999.999.005"].apply_outcome == "GONE"
    summary = chunk_result_summary(db_session, chunk)
    assert "Aktualisiert: 1" in summary
    assert "999.999.003" in summary
    assert "validation" in summary
    audits = list(
        db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "weclapp_article",
                AuditLog.actor_oid == "oid-writer",
            )
        )
    )
    assert audits
    assert all(a.detail.get("transform_run_id") == str(run.id) for a in audits)
    assert all(a.detail.get("transform_chunk_id") == str(chunk.id) for a in audits)


def test_auth_aborts_mid_chunk(db_session):
    arts = [
        _article("1", "999.999.001", "Alte Folie"),
        _article("2", "999.999.002", "Alte Folie"),
        _article("3", "999.999.003", "Alte Folie"),
    ]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    run = _preview(db_session, snap, _spec([a["articleNumber"] for a in arts]), client)
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")
    client.get_errors["2"] = WeclappError("nope", status_code=401)
    with pytest.raises(TransformAuthAbort) as exc:
        apply_chunk(db_session, chunk, oid="oid", client=client)
    assert str(exc.value) == MSG_INVALID
    from app.transform.apply import fail_chunk

    fail_chunk(db_session, chunk, str(exc.value))
    rows = list(
        db_session.scalars(
            select(TransformRow)
            .where(TransformRow.run_id == run.id)
            .order_by(TransformRow.article_number)
        )
    )
    assert rows[0].apply_outcome == "UPDATED"
    assert rows[1].apply_outcome is None
    assert rows[2].apply_outcome is None
    db_session.refresh(chunk)
    assert chunk.status == "failed"


def test_rerun_only_unattempted(db_session):
    arts = [
        _article("1", "999.999.001", "Alte Folie"),
        _article("2", "999.999.002", "Alte Folie"),
        _article("3", "999.999.003", "Alte Folie"),
    ]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    run = _preview(db_session, snap, _spec([a["articleNumber"] for a in arts]), client)
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")
    client.get_errors["2"] = WeclappError("nope", status_code=401)
    with pytest.raises(TransformAuthAbort):
        apply_chunk(db_session, chunk, oid="oid", client=client)
    first_puts = len(client.put_calls)
    client.get_errors.clear()
    apply_chunk(db_session, chunk, oid="oid", client=client)
    rows = {
        r.article_number: r
        for r in db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    }
    assert rows["999.999.001"].apply_outcome == "UPDATED"
    assert rows["999.999.002"].apply_outcome == "UPDATED"
    assert rows["999.999.003"].apply_outcome == "UPDATED"
    assert len(client.put_calls) == first_puts + 2


def test_conflict_not_reapplied(db_session):
    art = _article("1", "999.999.001", "Alte Folie")
    snap = _snapshot(db_session, [art])
    client = CatalogFake([art])
    run = _preview(db_session, snap, _spec(["999.999.001"]), client)
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")
    client.by_id["1"]["version"] = "50"
    apply_chunk(db_session, chunk, oid="oid", client=client)
    puts = len(client.put_calls)
    apply_chunk(db_session, chunk, oid="oid", client=client)
    assert len(client.put_calls) == puts
    row = db_session.scalars(
        select(TransformRow).where(TransformRow.run_id == run.id)
    ).one()
    assert row.apply_outcome == "CONFLICT"
    follow = preview_run_for_conflicts(db_session, run, created_by_oid="oid")
    assert follow.spec["scope"]["article_numbers"] == ["999.999.001"]
    assert follow.status == "previewing"


def test_per_row_commit_survives_interrupt(db_session, monkeypatch):
    arts = [
        _article("1", "999.999.001", "Alte Folie"),
        _article("2", "999.999.002", "Alte Folie"),
    ]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    run = _preview(db_session, snap, _spec([a["articleNumber"] for a in arts]), client)
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")

    from app.transform import apply as apply_mod

    real = apply_mod.update_article
    calls = {"n": 0}

    def wrapped(**kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("worker interrupt")
        return real(**kwargs)

    monkeypatch.setattr(apply_mod, "update_article", wrapped)
    with pytest.raises(RuntimeError, match="worker interrupt"):
        apply_chunk(db_session, chunk, oid="oid", client=client)
    rows = {
        r.article_number: r
        for r in db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    }
    assert rows["999.999.001"].apply_outcome == "UPDATED"
    assert rows["999.999.002"].apply_outcome is None


def test_audit_failure_after_put_records_unknown_and_is_not_retried(
    db_session, monkeypatch
):
    """PUT succeeded, audit_log write raised: must not look unattempted."""
    import app.article_write as write_mod
    import app.transform.apply as apply_mod
    from app.article_write import MSG_WRITE_UNKNOWN
    from app.jobs import _execute_job
    from app.models import Job

    art = _article("1", "999.999.001", "Alte Folie")
    snap = _snapshot(db_session, [art])
    client = CatalogFake([art])
    run = _preview(db_session, snap, _spec(["999.999.001"]), client)
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")

    def boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(write_mod, "record_audit_log", boom)
    monkeypatch.setattr(apply_mod, "weclapp_client_for", lambda _db, _oid: client)

    job = Job(
        job_type="article_transform_apply",
        payload={"transform_chunk_id": str(chunk.id), "actor_name": "Writer"},
        status="running",
        created_by_oid="oid",
        created_by_name="Writer",
    )
    db_session.add(job)
    db_session.commit()

    _execute_job(db_session, job)
    db_session.refresh(job)
    db_session.refresh(chunk)
    row = db_session.scalars(
        select(TransformRow).where(TransformRow.run_id == run.id)
    ).one()
    assert row.apply_outcome == "UNKNOWN"
    assert row.apply_detail == MSG_WRITE_UNKNOWN
    assert chunk.status == "applied"
    assert job.status == "succeeded"
    assert len(client.put_calls) == 1
    audits = list(
        db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "weclapp_article",
                AuditLog.entity_id == "1",
                AuditLog.actor_oid == "oid",
            )
        )
    )
    assert audits == []
    summary = chunk_result_summary(db_session, chunk)
    assert "Ausgang unbekannt: 1 (999.999.001)" in summary
    assert "nicht erneut anwenden" in summary

    apply_chunk(db_session, chunk, oid="oid", client=client)
    assert len(client.put_calls) == 1
    assert (
        db_session.scalars(
            select(TransformRow).where(TransformRow.run_id == run.id)
        ).one().apply_outcome
        == "UNKNOWN"
    )


def test_apply_job_registered():
    assert "article_transform_apply" in HANDLERS
    assert CHUNK_SIZE == 200


def test_declined_rows_persist_and_are_excluded_from_apply(db_session):
    arts = [
        _article("1", "999.999.001", "Alte Folie"),
        _article("2", "999.999.002", "Alte Folie"),
    ]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    run = _preview(db_session, snap, _spec([a["articleNumber"] for a in arts]), client)
    rows = list(
        db_session.scalars(
            select(TransformRow).where(TransformRow.run_id == run.id).order_by(TransformRow.article_number)
        )
    )
    keep = rows[0]
    drop = rows[1]
    chunk = approve_chunk(
        db_session,
        run,
        chunk_index=0,
        approver_oid="oid",
        selected_row_ids=[keep.id],
    )
    db_session.commit()
    assert chunk.row_ids == [str(keep.id)]
    db_session.refresh(drop)
    db_session.refresh(keep)
    assert drop.row_status == "DECLINED"
    assert keep.row_status == "CHANGED"
    apply_chunk(db_session, chunk, oid="oid", client=client)
    db_session.refresh(drop)
    db_session.refresh(keep)
    assert keep.apply_outcome == "UPDATED"
    assert drop.apply_outcome is None
    assert drop.row_status == "DECLINED"
    assert len(client.put_calls) == 1
    page_ids = {str(keep.id), str(drop.id)}
    assert str(drop.id) in page_ids



def _non_idem_spec(numbers: list[str]) -> TransformSpec:
    return TransformSpec.model_validate(
        {
            "scope": {"article_numbers": numbers},
            "fields": ["Prosema-Artikelname"],
            "operations": [
                {"op": "replace_literal", "search": "Profil", "replace": "ProfilX"}
            ],
        }
    )


def test_preview_summary_includes_non_idempotent_warning(db_session):
    art = _article("1", "999.999.001", "Profil")
    snap = _snapshot(db_session, [art])
    client = CatalogFake([art])
    spec = _non_idem_spec(["999.999.001"])
    run = _preview(db_session, snap, spec, client)
    text = preview_summary(run)
    assert "nicht idempotent" in text
    assert "manuell abgeglichen" in text


def test_rerun_refused_on_non_idempotent_spec(db_session, monkeypatch):
    arts = [
        _article("1", "999.999.001", "Profil"),
        _article("2", "999.999.002", "Profil"),
    ]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    spec = _non_idem_spec([a["articleNumber"] for a in arts])
    assert spec.idempotency_warnings
    run = _preview(db_session, snap, spec, client)
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")

    from app.transform import apply as apply_mod

    real = apply_mod.update_article
    calls = {"n": 0}

    def wrapped(**kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("worker interrupt")
        return real(**kwargs)

    monkeypatch.setattr(apply_mod, "update_article", wrapped)
    with pytest.raises(RuntimeError, match="worker interrupt"):
        apply_chunk(db_session, chunk, oid="oid", client=client)
    puts_after_first = len(client.put_calls)
    apply_chunk(db_session, chunk, oid="oid", client=client)
    assert len(client.put_calls) == puts_after_first
    rows = {
        r.article_number: r
        for r in db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    }
    assert rows["999.999.001"].apply_outcome == "UPDATED"
    assert rows["999.999.002"].apply_outcome == "REFUSED"
    from app.transform.schemas import MSG_RERUN_NON_IDEM

    assert rows["999.999.002"].apply_detail == MSG_RERUN_NON_IDEM


def test_reconcile_unknown_three_branches(db_session):
    from app.article_write import MSG_AUDIT_RECONSTRUCTED
    from app.transform.reconcile import (
        MSG_RECONCILE_DIVERGED,
        MSG_RECONCILE_LANDED,
        MSG_RECONCILE_SUMMARY,
        reconcile_unknown_chunk,
        reconcile_unknown_row,
    )

    landed = _article("1", "999.999.001", "Alte Folie")
    open_row = _article("2", "999.999.002", "Alte Folie")
    diverged = _article("3", "999.999.003", "Alte Folie")
    arts = [landed, open_row, diverged]
    snap = _snapshot(db_session, arts)
    client = CatalogFake(arts)
    run = _preview(db_session, snap, _spec([a["articleNumber"] for a in arts]), client)
    chunk = approve_chunk(db_session, run, chunk_index=0, approver_oid="oid")
    apply_chunk(db_session, chunk, oid="oid", actor_name="Writer", client=client)
    inline = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "weclapp_article",
            AuditLog.actor_oid == "oid",
            AuditLog.entity_id == "1",
        )
    ).first()
    assert inline is not None
    assert inline.detail.get("reconstructed") is False

    rows = {
        r.article_number: r
        for r in db_session.scalars(select(TransformRow).where(TransformRow.run_id == run.id))
    }
    for row in rows.values():
        row.apply_outcome = "UNKNOWN"
        row.apply_detail = "probe"
    db_session.commit()

    client.by_id["1"]["name"] = rows["999.999.001"].new_value
    client.by_id["2"]["name"] = rows["999.999.002"].old_value
    client.by_id["3"]["name"] = "Fremdänderung"
    puts_before = len(client.put_calls)

    one = reconcile_unknown_row(
        db_session,
        rows["999.999.001"],
        oid="oid",
        actor_name="Writer",
        client=client,
        chunk_id=str(chunk.id),
    )
    assert one.kind == "landed"
    assert one.message_de == MSG_RECONCILE_LANDED
    db_session.refresh(rows["999.999.001"])
    assert rows["999.999.001"].apply_outcome == "UPDATED"

    reconstructed = [
        a
        for a in db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "weclapp_article",
                AuditLog.actor_oid == "oid",
                AuditLog.entity_id == "1",
            )
        )
        if a.detail.get("reconstructed") is True
    ]
    assert len(reconstructed) == 1
    assert reconstructed[0].detail.get("reconstructed_note") == MSG_AUDIT_RECONSTRUCTED
    assert reconstructed[0].detail.get("version_before") == rows["999.999.001"].version_at_preview
    assert reconstructed[0].id != inline.id

    payload = reconcile_unknown_chunk(
        db_session, chunk, oid="oid", actor_name="Writer", client=client
    )
    assert payload["counts"] == {"landed": 0, "not_landed": 1, "diverged": 1}
    assert payload["summary"] == MSG_RECONCILE_SUMMARY.format(
        landed=0, not_landed=1, diverged=1
    )
    db_session.refresh(rows["999.999.002"])
    db_session.refresh(rows["999.999.003"])
    assert rows["999.999.002"].apply_outcome is None
    assert rows["999.999.003"].apply_outcome == "CONFLICT"
    assert rows["999.999.003"].apply_detail == MSG_RECONCILE_DIVERGED
    assert len(client.put_calls) == puts_before


def test_reconcile_wrapper_rejects_put_and_post():
    from app.transform.reconcile import GetOnlyWeclappClient

    class Inner:
        def put(self, *args, **kwargs):
            raise AssertionError("inner put should not run")

        def post(self, *args, **kwargs):
            raise AssertionError("inner post should not run")

    guarded = GetOnlyWeclappClient(Inner())
    with pytest.raises(AssertionError, match="must not PUT"):
        guarded.put("/article/id/1", json={})
    with pytest.raises(AssertionError, match="must not PUT"):
        guarded.post("/article", json={})

