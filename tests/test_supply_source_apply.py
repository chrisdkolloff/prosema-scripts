"""Mocked weclapp apply outcomes for the supply-source pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.jobs import HANDLERS
from app.models import Supplier, SupplySourceRow, SupplySourceRun
from app.supply_source_apply import apply_chunk
from app.supply_source_runs import set_rates
from scripts.weclapp.client import WeclappError

PLAIN = {"oid": "oid-apply", "name": "Dennis"}


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


def _supplier(db: Session) -> Supplier:
    row = db.scalars(select(Supplier).where(Supplier.supplier_number == "19998")).first()
    if row:
        return row
    row = Supplier(
        supplier_number="19998",
        weclapp_party_id="party-apply",
        name="Apply-Test",
        einkaufswaehrung="EUR",
        default_kurs=Decimal("0.93"),
        default_aufschlag=Decimal("0.50"),
        default_verkaufswaehrung="CHF",
        default_unit_id="3566",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _run_row(db: Session, *, intent: str, san: str = "SAN-1", **kwargs) -> tuple[SupplySourceRun, SupplySourceRow]:
    supplier = _supplier(db)
    run = SupplySourceRun(
        supplier_id=supplier.id,
        status="preview",
        source="pull",
        einkaufswaehrung="EUR",
        kurs=Decimal("0.93"),
        verkaufswaehrung="CHF",
        aufschlag=Decimal("0.50"),
        preis_eintritt=datetime(2026, 10, 1, tzinfo=UTC),
        created_by=PLAIN["oid"],
        created_by_name=PLAIN["name"],
        chunk_size=50,
    )
    db.add(run)
    db.flush()
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number=san,
        name="Teil",
        listenpreis=Decimal("100"),
        match_status="matched",
        row_intent=intent,
        weclapp_supply_source_id=kwargs.get("ss_id", "ss-1"),
        weclapp_version=kwargs.get("version", "3"),
        weclapp_article_id=kwargs.get("article_ids", ["art-1"])[0] if kwargs.get("article_ids", ["art-1"]) else None,
        article_number=kwargs.get("numbers", ["999.999.001"])[0] if kwargs.get("numbers", ["999.999.001"]) else None,
        included=kwargs.get("included", True),
        unit_id=kwargs.get("unit_id", "3566"),
    )
    set_rates(row, rabatt_1=Decimal("0"), rabatt_2=Decimal("0"), kein_rabatt=True)
    db.add(row)
    db.flush()
    return run, row


class FakeClient:
    def __init__(self, *, get_map=None, put_impl=None, post_impl=None):
        self.get_map = get_map or {}
        self.put_calls: list[dict] = []
        self.post_calls: list[dict] = []
        self.get_calls: list[str] = []
        self._put_impl = put_impl
        self._post_impl = post_impl

    def get(self, path, *, params=None):
        self.get_calls.append(path)
        if path == "/currency":
            return {"result": [{"id": "261", "name": "EUR"}]}
        if path in self.get_map:
            value = self.get_map[path]
            if isinstance(value, Exception):
                raise value
            return value
        if path.startswith("/article/id/"):
            aid = path.rsplit("/", 1)[-1]
            return {
                "id": aid,
                "version": "1",
                "supplySources": [],
                "primarySupplySourceId": None,
            }
        raise WeclappError("missing", status_code=404)

    def put(self, path, *, params=None, json=None):
        self.put_calls.append({"path": path, "params": params, "json": json})
        if self._put_impl:
            return self._put_impl(path, params, json)
        body = dict(json or {})
        body["version"] = str(int(body.get("version") or "0") + 1)
        return body

    def post(self, path, *, params=None, json=None):
        self.post_calls.append({"path": path, "params": params, "json": json})
        if self._post_impl:
            return self._post_impl(path, params, json)
        return {"id": "new-ss", "version": "0"}


def _live_ss(*, version="3", price="57.50", san="SAN-1"):
    return {
        "id": "ss-1",
        "version": version,
        "articleNumber": san,
        "name": "Teil",
        "articlePrices": [
            {
                "id": "p-open",
                "price": price,
                "currencyId": "261",
                "startDate": 1700000000000,
            }
        ],
    }


def test_apply_job_registered():
    assert "supply_source_apply" in HANDLERS


def test_unchanged_makes_zero_puts(db_session):
    run, row = _run_row(db_session, intent="price_only")
    client = FakeClient(
        get_map={"/articleSupplySource/id/ss-1": _live_ss(price="100.0000")}
    )
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    article_puts = [c for c in client.put_calls if c["path"].startswith("/article/id/")]
    ss_puts = [c for c in client.put_calls if "/articleSupplySource/" in c["path"]]
    assert ss_puts == []
    assert len(article_puts) == 1
    db_session.refresh(row)
    assert row.apply_outcome == "ATTACHED"
    assert (row.apply_detail or {}).get("group_outcome") == "UNCHANGED"


def test_conflict_does_not_put(db_session):
    run, row = _run_row(db_session, intent="price_only", version="3")
    client = FakeClient(get_map={"/articleSupplySource/id/ss-1": _live_ss(version="9")})
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    assert client.put_calls == []
    db_session.refresh(row)
    assert row.apply_outcome == "CONFLICT"


def test_auth_aborts_chunk_and_leaves_later_rows(db_session):
    run, first = _run_row(db_session, intent="price_only", san="A")
    second = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="B",
        listenpreis=Decimal("100"),
        match_status="matched",
        row_intent="price_only",
        weclapp_supply_source_id="ss-2",
        weclapp_version="1",
        weclapp_article_id="art-2",
        article_number="999.999.002",
    )
    set_rates(second, rabatt_1=Decimal("0"), rabatt_2=Decimal("0"), kein_rabatt=True)
    db_session.add(second)
    db_session.flush()
    client = FakeClient(
        get_map={
            "/articleSupplySource/id/ss-1": WeclappError("no", status_code=401),
            "/articleSupplySource/id/ss-2": _live_ss(),
        }
    )
    result = apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    assert result["aborted"] is True
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.apply_outcome == "AUTH"
    assert second.apply_outcome is None
    assert second.applied_at is None
    assert client.put_calls == []


def test_two_phase_create_survives_kill_between_post_and_attach(db_session):
    run, row = _run_row(
        db_session,
        intent="create",
        ss_id=None,
        article_ids=["art-1"],
        numbers=["999.999.001"],
    )
    row.weclapp_supply_source_id = None
    db_session.flush()
    posts = {"count": 0}

    def post_impl(path, params, json):
        posts["count"] += 1
        return {"id": "created-ss", "version": "0"}

    article = {
        "id": "art-1",
        "version": "1",
        "articleNumber": "999.999.001",
        "supplySources": [],
        "primarySupplySourceId": None,
    }
    client = FakeClient(
        get_map={
            "/article/id/art-1": article,
            "/articleSupplySource/id/created-ss": {
                "id": "created-ss",
                "version": "0",
                "articlePrices": [],
            },
        },
        post_impl=post_impl,
    )

    def kill(_ctx):
        raise RuntimeError("killed after POST")

    with pytest.raises(RuntimeError, match="killed"):
        apply_chunk(
            db_session,
            run,
            oid=PLAIN["oid"],
            actor_name="Dennis",
            client=client,
            chunk_index=0,
            after_create_hook=kill,
        )
    db_session.refresh(row)
    assert row.created_supply_source_id == "created-ss"
    assert posts["count"] == 1

    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    assert posts["count"] == 1
    db_session.refresh(row)
    assert row.apply_outcome == "ATTACHED"
    assert any(c["path"].startswith("/article/id/") for c in client.put_calls)


def test_price_only_put_keeps_history_and_ignore_missing(db_session):
    run, row = _run_row(db_session, intent="price_only")
    live = _live_ss(price="40.00")
    live["articlePrices"].append(
        {"id": "p-old", "price": "30", "currencyId": "261", "endDate": 1699999999999}
    )
    client = FakeClient(get_map={"/articleSupplySource/id/ss-1": live})
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    ss_puts = [c for c in client.put_calls if "/articleSupplySource/" in c["path"]]
    article_puts = [c for c in client.put_calls if c["path"].startswith("/article/id/")]
    assert len(ss_puts) == 1
    put = ss_puts[0]
    assert put["params"] == {"ignoreMissingProperties": "true"}
    prices = put["json"]["articlePrices"]
    assert len(prices) == 3
    assert any(p.get("id") == "p-old" for p in prices)
    assert any(p.get("id") == "p-open" and "endDate" in p for p in prices)
    new_rows = [p for p in prices if "id" not in p]
    assert new_rows
    assert Decimal(str(new_rows[0]["price"])) == Decimal("100")
    assert len(article_puts) == 1
    db_session.refresh(row)
    assert row.apply_outcome == "ATTACHED"
    assert (row.apply_detail or {}).get("group_outcome") == "PRICE_UPDATED"


def test_overlap_is_rejected_without_retry(db_session):
    run, row = _run_row(db_session, intent="price_only")
    live = _live_ss(price="40.00")
    puts = {"count": 0}

    def put_impl(path, params, json):
        puts["count"] += 1
        raise WeclappError(
            "overlap",
            status_code=400,
            detail={
                "detail": "validation failed",
                "messages": [
                    {"message": "The price with ID 399567 and the new price overlap."}
                ],
            },
        )

    client = FakeClient(
        get_map={"/articleSupplySource/id/ss-1": live},
        put_impl=put_impl,
    )
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    assert puts["count"] == 1
    db_session.refresh(row)
    assert row.apply_outcome == "REJECTED"
    assert "Preis-Eintritt" in (row.apply_detail or {}).get("message", "")


def test_renumber_puts_and_never_posts(db_session):
    run, row = _run_row(db_session, intent="renumber", san="NEW-SAN")
    client = FakeClient(get_map={"/articleSupplySource/id/ss-1": _live_ss(san="OLD-SAN")})
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    assert client.post_calls == []
    ss_puts = [c for c in client.put_calls if "/articleSupplySource/" in c["path"]]
    article_puts = [c for c in client.put_calls if c["path"].startswith("/article/id/")]
    assert len(ss_puts) == 1
    assert ss_puts[0]["json"]["articleNumber"] == "NEW-SAN"
    assert len(article_puts) == 1
    db_session.refresh(row)
    assert row.apply_outcome == "ATTACHED"
    assert (row.apply_detail or {}).get("group_outcome") == "RENUMBERED"


def test_gone_on_404(db_session):
    run, row = _run_row(db_session, intent="price_only")
    client = FakeClient()
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    db_session.refresh(row)
    assert row.apply_outcome == "GONE"
    assert client.put_calls == []


def test_non_price_updates_honour_field_overrides():
    from app.supply_source_apply import _non_price_updates

    row = SupplySourceRow(
        supplier_article_number="X",
        name="weclapp-name",
        template_name="template-name",
        ean="111",
        template_ean="222",
        field_overrides={"name": "weclapp", "ean": "template"},
    )
    extra = _non_price_updates(
        row, {"name": "weclapp-name", "ean": "111", "minimumPurchaseQuantity": None}
    )
    assert "name" not in extra
    assert extra["ean"] == "222"


def test_shared_ss_one_put_two_article_puts(db_session):
    run, first = _run_row(
        db_session,
        intent="price_only",
        article_ids=["art-a"],
        numbers=["999.030.0040"],
    )
    second = SupplySourceRow(
        run_id=run.id,
        supplier_article_number=first.supplier_article_number,
        name="Teil",
        listenpreis=Decimal("100"),
        match_status="matched",
        row_intent="price_only",
        weclapp_supply_source_id="ss-1",
        weclapp_version="3",
        weclapp_article_id="art-b",
        article_number="999.030.0070",
        unit_id="3566",
        included=True,
    )
    set_rates(second, rabatt_1=Decimal("0"), rabatt_2=Decimal("0"), kein_rabatt=True)
    db_session.add(second)
    db_session.flush()
    live = _live_ss(price="40.00")
    client = FakeClient(get_map={"/articleSupplySource/id/ss-1": live})
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    ss_puts = [c for c in client.put_calls if "/articleSupplySource/" in c["path"]]
    article_puts = [c for c in client.put_calls if c["path"].startswith("/article/id/")]
    assert len(ss_puts) == 1
    assert {c["path"] for c in article_puts} == {"/article/id/art-a", "/article/id/art-b"}
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.apply_outcome == "ATTACHED"
    assert second.apply_outcome == "ATTACHED"
    assert (first.apply_detail or {}).get("group_outcome") == "PRICE_UPDATED"


def test_ss_write_failure_skips_article_puts(db_session):
    run, first = _run_row(
        db_session,
        intent="price_only",
        article_ids=["art-a"],
        numbers=["999.030.0040"],
        version="9",
    )
    second = SupplySourceRow(
        run_id=run.id,
        supplier_article_number=first.supplier_article_number,
        listenpreis=Decimal("100"),
        match_status="matched",
        row_intent="price_only",
        weclapp_supply_source_id="ss-1",
        weclapp_version="9",
        weclapp_article_id="art-b",
        article_number="999.030.0070",
        unit_id="3566",
        included=True,
    )
    set_rates(second, rabatt_1=Decimal("0"), rabatt_2=Decimal("0"), kein_rabatt=True)
    db_session.add(second)
    db_session.flush()
    client = FakeClient(get_map={"/articleSupplySource/id/ss-1": _live_ss(version="3")})
    apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    assert client.put_calls == []
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.apply_outcome == "CONFLICT"
    assert second.apply_outcome == "CONFLICT"


def test_excluded_ean_row_is_not_applied(db_session):
    run, row = _run_row(
        db_session,
        intent="attach",
        included=False,
    )
    client = FakeClient(get_map={"/articleSupplySource/id/ss-1": _live_ss()})
    result = apply_chunk(
        db_session, run, oid=PLAIN["oid"], actor_name="Dennis", client=client, chunk_index=0
    )
    assert result["applied"] == 0
    assert client.put_calls == []
    db_session.refresh(row)
    assert row.apply_outcome is None

