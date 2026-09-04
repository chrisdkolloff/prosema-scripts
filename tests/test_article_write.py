"""Single-article write path — faked weclapp, every outcome."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.article_write import (
    ArticleWriteAuditDetail,
    ArticleWriteFieldChange,
    ArticleWriteOutcome,
    live_field_value,
    update_article,
)
from app.models import AuditLog
from core.article_write_fields import CustomAttributeResolver
from scripts.weclapp.client import WeclappError

PASS1_DEFS = [
    {"id": str(1000 + i), "label": label}
    for i, label in enumerate(
        [
            "Grundmaterial",
            "Oberfläche",
            "Farbe",
            "Produktfamilie",
            "Rabattcode",
            "Verkaufseinheit",
            "Verpackung",
            "VPE 1",
            "VPE 2",
            "VPE 3",
            "Breite in mm",
            "Höhe in mm",
            "Länge in cm",
            "Gewichtseinheit",
            "Produkt-ID (Prosema)",
            "Varianten-ID (Prosema)",
        ]
    )
]


def _article(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "353023",
        "articleNumber": "999.999.001",
        "version": "10",
        "name": "Alte Folie",
        "longText": "<p>Alte Folie</p>",
        "shortDescription1": "Alte Folie",
        "matchCode": "OLD",
        "customAttributes": [
            {"attributeDefinitionId": "1002", "stringValue": "Grau"},
        ],
    }
    row.update(overrides)
    return row


def _ids_from_in_param(raw: Any) -> set[str]:
    text = str(raw or "").strip()
    if not text:
        return set()
    inner = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    return {part.strip() for part in inner.split(",") if part.strip()}


class FakeWeclappClient:
    def __init__(
        self,
        article: dict[str, Any],
        *,
        definitions: list[dict[str, Any]] | None = None,
        put_error: WeclappError | None = None,
        get_error: WeclappError | None = None,
    ) -> None:
        self.article = copy.deepcopy(article)
        self.definitions = definitions if definitions is not None else list(PASS1_DEFS)
        self.put_error = put_error
        self.get_error = get_error
        self.get_calls: list[str] = []
        self.put_calls: list[dict[str, Any]] = []
        self.iter_calls: list[tuple[str, int | None]] = []

    def get(self, path: str, *, params=None) -> Any:
        self.get_calls.append(path)
        if path.rstrip("/") == "/article" or path == "/article":
            if self.get_error is not None and self.get_error.status_code != 404:
                raise self.get_error
            if self.get_error is not None and self.get_error.status_code == 404:
                return {"result": []}
            wanted = _ids_from_in_param((params or {}).get("id-in"))
            art = copy.deepcopy(self.article)
            if wanted and str(art["id"]) not in wanted:
                return {"result": []}
            like = str((params or {}).get("articleNumber-like") or "")
            if like.endswith("%") and not str(art.get("articleNumber") or "").startswith(like[:-1]):
                return {"result": []}
            return {"result": [art]}
        if self.get_error is not None and path.startswith("/article/id/"):
            raise self.get_error
        if path == f"/article/id/{self.article['id']}":
            return copy.deepcopy(self.article)
        raise AssertionError(f"unexpected GET {path}")

    def put(self, path: str, *, params=None, json=None) -> Any:
        self.put_calls.append({"path": path, "params": params, "json": json})
        if self.put_error is not None:
            raise self.put_error
        body = dict(json or {})
        version_after = str(int(str(self.article["version"])) + 1)
        updated = copy.deepcopy(self.article)
        for key, value in body.items():
            if key == "customAttributes":
                continue
            updated[key] = value
        updated["version"] = version_after
        self.article = updated
        return copy.deepcopy(updated)

    def iter_pages(self, entity: str, *, params=None, page_size=None):
        self.iter_calls.append((entity, page_size))
        if entity == "article":
            payload = self.get("/article", params=dict(params or {}))
            yield from payload.get("result") or []
            return
        yield from self.definitions


@pytest.fixture
def db_session():
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _run(db, client, changes, **kwargs):
    resolver = CustomAttributeResolver(client)
    return update_article(
        db=db,
        client=client,
        resolver=resolver,
        article_id=client.article["id"],
        changes=changes,
        actor_oid="oid-writer",
        actor_name="Writer",
        **kwargs,
    )


def test_updated_writes_audit_that_round_trips(db_session):
    client = FakeWeclappClient(_article())
    result = _run(db_session, client, {"Prosema-Artikelname": "Neue Folie"})
    assert result.outcome is ArticleWriteOutcome.UPDATED
    assert result.put_sent
    assert len(client.put_calls) == 1
    assert client.put_calls[0]["params"] == {"ignoreMissingProperties": "true"}
    assert client.put_calls[0]["json"]["version"] == "10"
    assert client.put_calls[0]["json"]["name"] == "Neue Folie"
    assert result.version_after == "11"
    assert result.audit is not None
    parsed = ArticleWriteAuditDetail.model_validate(result.audit.model_dump())
    assert parsed.fields[0].old == "Alte Folie"
    assert parsed.fields[0].new == "Neue Folie"
    db_session.flush()
    row = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "weclapp_article",
            AuditLog.actor_oid == "oid-writer",
        )
    ).first()
    assert row is not None
    assert row.action == "updated"
    again = ArticleWriteAuditDetail.model_validate(row.detail)
    assert again == parsed


def test_expected_version_sent_on_put(db_session):
    client = FakeWeclappClient(_article())
    result = _run(
        db_session,
        client,
        {"Prosema-Artikelname": "Neue Folie"},
        expected_version="10",
        transform_run_id="run-1",
        transform_chunk_id="chunk-1",
    )
    assert result.outcome is ArticleWriteOutcome.UPDATED
    assert client.put_calls[0]["json"]["version"] == "10"
    assert result.audit is not None
    assert result.audit.transform_run_id == "run-1"
    assert result.audit.transform_chunk_id == "chunk-1"


def test_unchanged_sends_no_put(db_session):
    client = FakeWeclappClient(_article())
    result = _run(db_session, client, {"Prosema-Artikelname": "Alte Folie"})
    assert result.outcome is ArticleWriteOutcome.UNCHANGED
    assert client.put_calls == []
    db_session.flush()
    rows = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "weclapp_article",
            AuditLog.actor_oid == "oid-writer",
        )
    ).all()
    assert rows == []


def test_conflict_409_does_not_retry(db_session):
    err = WeclappError("stale", status_code=409, detail={"error": "optimisticLock"})
    client = FakeWeclappClient(_article(), put_error=err)
    result = _run(db_session, client, {"Prosema-Artikelname": "Neue Folie"})
    assert result.outcome is ArticleWriteOutcome.CONFLICT
    assert len(client.put_calls) == 1
    assert result.audit is not None
    assert result.audit.version_after is None
    db_session.flush()
    row = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "weclapp_article",
            AuditLog.actor_oid == "oid-writer",
        )
    ).one()
    assert row.action == "conflict"


def test_rejected_400_captures_detail(db_session):
    detail = {"error": "validation", "attribute": "name"}
    err = WeclappError("bad", status_code=400, detail=detail)
    client = FakeWeclappClient(_article(), put_error=err)
    result = _run(db_session, client, {"Prosema-Artikelname": "Neue Folie"})
    assert result.outcome is ArticleWriteOutcome.REJECTED
    assert result.weclapp_detail == detail
    db_session.flush()
    row = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "weclapp_article",
            AuditLog.actor_oid == "oid-writer",
        )
    ).one()
    assert row.action == "rejected"


def test_unavailable_on_network_error(db_session):
    err = WeclappError("Netzwerkfehler bei PUT /article", status_code=None)
    client = FakeWeclappClient(_article(), put_error=err)
    result = _run(db_session, client, {"Prosema-Artikelname": "Neue Folie"})
    assert result.outcome is ArticleWriteOutcome.UNAVAILABLE
    db_session.flush()
    rows = db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_type == "weclapp_article",
            AuditLog.actor_oid == "oid-writer",
        )
    ).all()
    assert rows == []


def test_unavailable_on_503(db_session):
    err = WeclappError("down", status_code=503, detail="no")
    client = FakeWeclappClient(_article(), put_error=err)
    result = _run(db_session, client, {"Prosema-Artikelname": "Neue Folie"})
    assert result.outcome is ArticleWriteOutcome.UNAVAILABLE


def test_refused_forbidden_key_makes_no_weclapp_call(db_session):
    client = FakeWeclappClient(_article())
    result = _run(db_session, client, {"Prosema-Artikelnummer": "999.999.002"})
    assert result.outcome is ArticleWriteOutcome.REFUSED
    assert "Prosema-Artikelnummer" in (result.message or "")
    assert client.get_calls == []
    assert client.put_calls == []
    assert client.iter_calls == []


def test_refused_later_key(db_session):
    client = FakeWeclappClient(_article())
    result = _run(db_session, client, {"Aktiv": "Nein"})
    assert result.outcome is ArticleWriteOutcome.REFUSED
    assert client.put_calls == []


def test_guard_blocks_live_article_number(db_session):
    client = FakeWeclappClient(_article(articleNumber="020.020.0010"))
    result = _run(db_session, client, {"Prosema-Artikelname": "X"})
    assert result.outcome is ArticleWriteOutcome.REFUSED
    assert "allow_live" in (result.message or "")
    assert client.put_calls == []
    assert client.get_calls == ["/article/id/353023"]


def test_allow_live_lifts_guard(db_session):
    client = FakeWeclappClient(_article(articleNumber="020.020.0010"))
    result = _run(db_session, client, {"Prosema-Artikelname": "X"}, allow_live=True)
    assert result.outcome is ArticleWriteOutcome.UPDATED
    assert len(client.put_calls) == 1


def test_update_article_category_puts_id_only(db_session):
    from app.article_write import update_article_category

    client = FakeWeclappClient(_article(articleNumber="999.999.001", articleCategoryId="old"))
    result = update_article_category(
        db=db_session,
        client=client,
        article_id=client.article["id"],
        category_id="c130",
        actor_oid="oid-writer",
        actor_name="Writer",
        allow_live=True,
    )
    assert result.outcome is ArticleWriteOutcome.UPDATED
    body = client.put_calls[0]["json"]
    assert body == {"version": "10", "articleCategoryId": "c130"}
    assert client.put_calls[0]["params"] == {"ignoreMissingProperties": "true"}


def test_auth_401_uses_token_message(db_session):
    from app.weclapp import MSG_INVALID

    err = WeclappError("nope", status_code=401)
    client = FakeWeclappClient(_article(), get_error=err)
    result = _run(db_session, client, {"Prosema-Artikelname": "X"})
    assert result.outcome is ArticleWriteOutcome.AUTH
    assert result.message == MSG_INVALID
    assert client.put_calls == []


def test_auth_403_uses_licence_message(db_session):
    from app.weclapp import MSG_NO_LICENCE

    err = WeclappError("nope", status_code=403)
    client = FakeWeclappClient(_article(), get_error=err)
    result = _run(db_session, client, {"Prosema-Artikelname": "X"})
    assert result.outcome is ArticleWriteOutcome.AUTH
    assert result.message == MSG_NO_LICENCE
    assert client.put_calls == []


def test_gone_404(db_session):
    err = WeclappError("missing", status_code=404)
    client = FakeWeclappClient(_article(), get_error=err)
    result = _run(db_session, client, {"Prosema-Artikelname": "X"})
    assert result.outcome is ArticleWriteOutcome.GONE
    assert client.put_calls == []
    client = FakeWeclappClient(_article())
    resolver = CustomAttributeResolver(client)
    resolver.load()
    html = live_field_value(client.article, "Prosema-Langtext", resolver)
    assert html == "<p>Alte Folie</p>"


def test_audit_detail_model_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        ArticleWriteAuditDetail.model_validate(
            {
                "weclapp_id": "1",
                "article_number": "999.999.001",
                "version_before": "1",
                "fields": [],
                "extra": True,
            }
        )
    ArticleWriteFieldChange(
        snapshot_key="Prosema-Artikelname",
        target="name",
        location="NATIVE",
        attribute_definition_id=None,
        old="a",
        new="b",
    )
