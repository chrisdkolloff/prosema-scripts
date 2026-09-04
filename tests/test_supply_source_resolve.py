"""Supply-source resolve job and preview grid (sibling to frozen CSV export)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.jobs import HANDLERS
from app.main import app
from app.models import (
    Supplier,
    SupplierArticleAlias,
    SupplySourceRow,
    SupplySourceRun,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
    WeclappSupplySourcePrice,
)
from app.supply_source_resolve import run_resolve
from app.supply_source_runs import (
    apply_bulk_rates,
    approval_blockers,
    approve_run,
    can_approve,
    set_rates,
)

PLAIN_USER = {
    "oid": "user-oid-ss-resolve",
    "name": "Dennis",
    "email": "user@example.com",
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
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def _now():
    return datetime.now(UTC)


def _supplier(db: Session) -> Supplier:
    existing = db.scalars(
        select(Supplier).where(Supplier.supplier_number == "19999")
    ).first()
    if existing:
        return existing
    row = Supplier(
        supplier_number="19999",
        weclapp_party_id="party-test-ss",
        name="Testlieferant",
        einkaufswaehrung="EUR",
        default_kurs=Decimal("0.93"),
        default_aufschlag=Decimal("0.50"),
        default_verkaufswaehrung="CHF",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _run(db: Session, supplier: Supplier) -> SupplySourceRun:
    run = SupplySourceRun(
        supplier_id=supplier.id,
        status="running",
        source="pull",
        einkaufswaehrung="EUR",
        kurs=Decimal("0.93"),
        verkaufswaehrung="CHF",
        aufschlag=Decimal("0.50"),
        created_by=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
    )
    db.add(run)
    db.flush()
    return run


def _ss(
    db: Session,
    *,
    ss_id: str,
    san: str,
    name: str = "Teil",
    ean: str | None = None,
    price: str = "10.0000",
    currency: str = "EUR",
):
    now = _now()
    row = WeclappSupplySource(
        weclapp_id=ss_id,
        supplier_party_id="party-test-ss",
        supplier_number="19999",
        supplier_article_number=san,
        name=name,
        ean=ean,
        weclapp_version="3",
        last_seen_at=now,
    )
    db.add(row)
    db.add(
        WeclappSupplySourcePrice(
            supply_source_weclapp_id=ss_id,
            price=Decimal(price),
            currency_code=currency,
            end_date=None,
        )
    )
    db.flush()
    return row


def _article(db: Session, *, aid: str, number: str, ean: str | None = None, code: str | None = None):
    db.add(
        WeclappArticle(
            weclapp_article_id=aid,
            article_number=number,
            name="Artikel",
            ean=ean,
            rabattcode=code,
            weclapp_version="1",
            last_seen_at=_now(),
        )
    )
    db.flush()


def _link(db: Session, *, ss_id: str, aid: str, number: str):
    db.add(
        WeclappSupplySourceLink(
            supply_source_weclapp_id=ss_id,
            weclapp_article_id=aid,
            article_number=number,
            supplier_party_id="party-test-ss",
        )
    )
    db.flush()


def test_resolve_job_registered():
    assert "supply_source_resolve" in HANDLERS


def test_shared_ss_one_row_two_articles(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-ss-shared", san="TST-SHARED")
    _article(db_session, aid="tst-a1", number="999.030.0040", code="A")
    _article(db_session, aid="tst-a2", number="999.030.0070", code="A")
    _link(db_session, ss_id="tst-ss-shared", aid="tst-a1", number="999.030.0040")
    _link(db_session, ss_id="tst-ss-shared", aid="tst-a2", number="999.030.0070")
    run = _run(db_session, supplier)
    result = run_resolve(db_session, run, oid="x", skip_index=True)
    rows = list(db_session.scalars(select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)))
    assert result["row_count"] == 1
    assert len(rows) == 1
    assert sorted(rows[0].resolved_article_numbers) == ["999.030.0040", "999.030.0070"]
    assert rows[0].match_tier == 1
    assert rows[0].row_intent == "price_only"
    assert rows[0].match_status == "matched"


def test_orphan_ss_resolves_attach_via_ean(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-ss-orphan", san="TST-ORPHAN", ean="9990000000001")
    _article(db_session, aid="tst-a-or", number="999.010.0010", ean="9990000000001")
    run = _run(db_session, supplier)
    run_resolve(db_session, run, oid="x", skip_index=True)
    row = db_session.scalars(
        select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
    ).one()
    assert row.row_intent == "attach"
    assert row.match_status == "matched"
    assert row.match_tier == 3
    assert row.resolved_article_numbers == ["999.010.0010"]


def test_unknown_san_unmatched_blocks_approval(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    db_session.add(
        SupplySourceRow(run_id=run.id, supplier_article_number="UNKNOWN-SAN")
    )
    db_session.flush()
    run_resolve(db_session, run, oid="x", skip_index=True)
    row = db_session.scalars(
        select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
    ).one()
    assert row.match_status == "unmatched"
    assert row.row_intent is None
    run.status = "preview"
    db_session.flush()
    assert can_approve([row]) is False
    with pytest.raises(Exception, match="Freigabe"):
        approve_run(db_session, run)


def test_blank_rates_block_kein_rabatt_does_not(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-ss1", san="TST-SAN-1")
    _article(db_session, aid="tst-b1", number="999.010.1010", code="A")
    _link(db_session, ss_id="tst-ss1", aid="tst-b1", number="999.010.1010")
    run = _run(db_session, supplier)
    run_resolve(db_session, run, oid="x", skip_index=True)
    row = db_session.scalars(
        select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
    ).one()
    run.status = "preview"
    db_session.flush()
    assert row.discount_set is False
    assert approval_blockers([row])["discount_unset"] == 1
    set_rates(row, rabatt_1=None, rabatt_2=None, kein_rabatt=True)
    db_session.flush()
    assert row.discount_set is True
    assert row.rabatt_1 == Decimal(0)
    assert approval_blockers([row])["discount_unset"] == 0
    approve_run(db_session, run)
    db_session.refresh(run)
    assert run.status == "approved"


def test_bulk_rates_by_rabattcode(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-ss-a1", san="A-1")
    _ss(db_session, ss_id="tst-ss-a2", san="A-2")
    _ss(db_session, ss_id="tst-ss-b", san="B-1")
    _article(db_session, aid="tst-ba1", number="999.010.2010", code="A")
    _article(db_session, aid="tst-ba2", number="999.010.2020", code="A")
    _article(db_session, aid="tst-bb1", number="999.010.2030", code="B")
    _link(db_session, ss_id="tst-ss-a1", aid="tst-ba1", number="999.010.2010")
    _link(db_session, ss_id="tst-ss-a2", aid="tst-ba2", number="999.010.2020")
    _link(db_session, ss_id="tst-ss-b", aid="tst-bb1", number="999.010.2030")
    run = _run(db_session, supplier)
    run_resolve(db_session, run, oid="x", skip_index=True)
    run.status = "preview"
    db_session.flush()
    applied = apply_bulk_rates(
        db_session,
        run,
        rabattcode="A",
        rabatt_1=Decimal("0.50"),
        rabatt_2=Decimal("0.10"),
    )
    assert applied == 2
    rows = {
        r.supplier_article_number: r
        for r in db_session.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        )
    }
    assert rows["A-1"].discount_set is True
    assert rows["A-2"].rabatt_1 == Decimal("0.50")
    assert rows["B-1"].discount_set is False


def test_renumber_when_alias_points_at_existing_supplier_link(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-ss-old", san="OLD-SAN")
    _article(db_session, aid="tst-rn1", number="999.010.3010")
    _link(db_session, ss_id="tst-ss-old", aid="tst-rn1", number="999.010.3010")
    db_session.add(
        SupplierArticleAlias(
            supplier_id=supplier.id,
            supplier_article_number="NEW-SAN",
            article_number="999.010.3010",
            weclapp_article_id="tst-rn1",
            source="manual",
        )
    )
    run = _run(db_session, supplier)
    db_session.add(SupplySourceRow(run_id=run.id, supplier_article_number="NEW-SAN"))
    db_session.flush()
    run_resolve(db_session, run, oid="x", skip_index=True)
    row = db_session.scalars(
        select(SupplySourceRow).where(SupplySourceRow.supplier_article_number == "NEW-SAN")
    ).one()
    assert row.row_intent == "renumber"
    assert row.weclapp_supply_source_id == "tst-ss-old"
    assert row.match_tier == 2


def test_list_and_legacy_export_pages(user_client):
    neu = user_client.get("/bezugsquellen/neu")
    assert neu.status_code == 200
    assert "Bezugsquellen abgleichen" in neu.text
    assert "Vorlage aus weclapp erzeugen" in neu.text
    legacy = user_client.get("/bezugsquellen")
    assert legacy.status_code == 200
    assert "Bezugsquellenexport" in legacy.text
    js = user_client.get("/static/supply_source_grid.js")
    assert js.status_code == 200
    assert b"Kein Rabatt" in js.content or b"kein_rabatt" in js.content


def test_preview_grid_and_bulk_http(user_client, db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-http-ss", san="TST-HTTP")
    _article(db_session, aid="tst-http-a", number="999.010.4010", code="A")
    _link(db_session, ss_id="tst-http-ss", aid="tst-http-a", number="999.010.4010")
    run = _run(db_session, supplier)
    run_resolve(db_session, run, oid="x", skip_index=True)
    run.status = "preview"
    db_session.flush()
    page = user_client.get(f"/bezugsquellen/neu/{run.id}")
    assert page.status_code == 200
    assert "ohne Rabattsatz" in page.text
    assert "supply_source_grid.js" in page.text
    blocked = user_client.post(f"/bezugsquellen/neu/{run.id}/freigeben")
    assert blocked.status_code in {303, 200}
    bulk = user_client.post(
        f"/bezugsquellen/neu/{run.id}/rabatte",
        json={"rabattcode": "A", "rabatt_1": "50", "rabatt_2": "10"},
    )
    assert bulk.status_code == 200
    body = bulk.json()
    assert body["applied"] == 1
    approve = user_client.post(f"/bezugsquellen/neu/{run.id}/freigeben", follow_redirects=False)
    assert approve.status_code == 303
    db_session.refresh(run)
    assert run.status == "approved"


def test_create_pull_enqueues_without_touching_export_tables(user_client, db_session):
    supplier = _supplier(db_session)
    with patch("app.jobs.enqueue") as enqueue:
        import uuid

        from app.models import Job

        job = Job(
            id=uuid.uuid4(),
            job_type="supply_source_resolve",
            payload={},
            status="queued",
            created_by_oid="x",
            created_by_name="x",
        )
        db_session.add(job)
        db_session.flush()
        enqueue.return_value = job
        response = user_client.post(
            "/bezugsquellen/neu/abfragen",
            data={"supplier_id": str(supplier.id)},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert "/bezugsquellen/neu/" in response.headers["location"]
    enqueue.assert_called_once()
    assert enqueue.call_args[0][1] == "supply_source_resolve"
