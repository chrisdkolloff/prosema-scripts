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
from app.config import settings
from app.models import (
    ArticleSnapshot,
    ArticleSnapshotRow,
    Supplier,
    SupplierArticleAlias,
    SupplySourceRow,
    SupplySourceRun,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
    WeclappSupplySourcePrice,
)
from app.supply_source_resolve import SAN_FIELDS, run_resolve
from app.weclapp import MSG_INVALID
from scripts.weclapp.client import WeclappError
from app.supply_source_runs import (
    SupplySourceRunError,
    apply_bulk_rates,
    apply_edits,
    approval_blockers,
    approve_run,
    build_grid_config,
    can_approve,
    derived_prices,
    format_pct,
    parse_aufschlag_percent,
    parse_rate,
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
        preis_eintritt=_now().replace(second=0, microsecond=0),
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
        unit_id="3566",
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
            unit_id="3566",
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
    assert result["row_count"] == 2
    assert len(rows) == 2
    assert sorted(r.article_number for r in rows) == ["999.030.0040", "999.030.0070"]
    assert {r.supplier_article_number for r in rows} == {"TST-SHARED"}
    assert all(r.included is True for r in rows)
    assert all(r.match_tier == 1 for r in rows)
    assert all(r.unit_id == "3566" for r in rows)
    assert all(r.row_intent == "price_only" for r in rows)
    assert all(r.match_status == "matched" for r in rows)
    _assert_san_fields_aligned(rows)


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
    assert row.article_number == "999.010.0010"
    assert row.included is False


def test_auth_failure_skips_live_index_and_keeps_preview(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-ss-offline", san="TST-OFF")
    _article(db_session, aid="tst-a-off", number="999.010.5010", code="A")
    _link(db_session, ss_id="tst-ss-offline", aid="tst-a-off", number="999.010.5010")
    run = _run(db_session, supplier)
    with patch(
        "app.supply_source_resolve.pull_supply_source_index",
        side_effect=WeclappError("nope", status_code=401),
    ):
        run_resolve(db_session, run, oid="x", skip_index=False)
    db_session.refresh(run)
    assert run.status == "preview"
    assert MSG_INVALID in (run.error or "")
    row = db_session.scalars(
        select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
    ).one()
    assert row.match_tier == 1
    assert row.article_number == "999.010.5010"


def test_ean_match_from_artikeluebersicht_when_article_mirror_empty(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.source = "upload"
    db_session.add(
        SupplySourceRow(
            run_id=run.id,
            supplier_article_number="SNAP-SAN",
            ean="0001112223334",
            name="Profil",
        )
    )
    snapshot = ArticleSnapshot(
        status="complete",
        created_by_oid="oid-snap",
        created_by_name="Test",
        weclapp_tenant=settings.weclapp_tenant.strip() or "local",
        row_count=1,
        columns=[],
    )
    db_session.add(snapshot)
    db_session.flush()
    db_session.add(
        ArticleSnapshotRow(
            snapshot_id=snapshot.id,
            position=0,
            data={"GTIN (EAN-Nummer)": "0001112223334", "Rabattcode": "DURAL"},
            article_number="999.010.8010",
            article_name="Profil",
            weclapp_id="snap-art-1",
        )
    )
    db_session.flush()
    with patch.object(settings, "weclapp_tenant", snapshot.weclapp_tenant):
        with patch(
            "app.supply_source_resolve._latest_completed_snapshot",
            return_value=snapshot,
        ):
            run_resolve(db_session, run, oid="x", skip_index=True)
    row = db_session.scalars(
        select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
    ).one()
    assert row.match_status == "matched"
    assert row.match_tier == 3
    assert row.article_number == "999.010.8010"
    assert row.weclapp_article_id == "snap-art-1"
    assert row.row_intent == "create"
    assert row.rabattcode == "DURAL"


def test_retry_failed_run_requeues(user_client, db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.status = "failed"
    run.error = MSG_INVALID
    db_session.flush()
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
            f"/bezugsquellen/neu/{run.id}/erneut",
            follow_redirects=False,
        )
    assert response.status_code == 303
    db_session.refresh(run)
    assert run.status == "running"
    enqueue.assert_called_once()
    assert enqueue.call_args[0][1] == "supply_source_resolve"


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
        approve_run(db_session, run, {"oid": "x", "name": "Dennis"})


def test_parse_aufschlag_percent():
    assert parse_aufschlag_percent("50") == Decimal("0.50")
    assert parse_aufschlag_percent("50.00") == Decimal("0.50")
    assert parse_aufschlag_percent("50,5") == Decimal("0.505")
    assert parse_aufschlag_percent("50%") == Decimal("0.50")


def test_parse_rate_percent_not_fraction():
    assert parse_rate("50") == Decimal("0.5")
    assert parse_rate("0") == Decimal("0")
    assert parse_rate("100") == Decimal("1")
    assert parse_rate("12,5") == Decimal("0.125")
    assert parse_rate("12.5") == Decimal("0.125")
    assert format_pct(parse_rate("50")) == "50"
    with pytest.raises(SupplySourceRunError, match="Bitte in Prozent"):
        parse_rate("0.5")
    with pytest.raises(SupplySourceRunError, match="über 100"):
        parse_rate("101")
    with pytest.raises(SupplySourceRunError, match="negativ"):
        parse_rate("-1")


def test_grid_cell_rate_uses_parse_rate(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.status = "preview"
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="CELL-RATE",
        listenpreis=Decimal("100"),
        match_status="unmatched",
    )
    db_session.add(row)
    db_session.flush()
    with pytest.raises(SupplySourceRunError, match="Bitte in Prozent"):
        apply_edits(
            db_session, run, [{"row_id": row.id, "field": "rabatt_1", "value": "0.5"}]
        )
    apply_edits(db_session, run, [{"row_id": row.id, "field": "rabatt_1", "value": "50"}])
    db_session.refresh(row)
    assert row.rabatt_1 == Decimal("0.50")
    assert row.discount_set is True
    grid = build_grid_config(run, [row])
    r1_x = grid["fields"].index("rabatt_1")
    assert grid["data"][0][r1_x] == "50"
    unit_col = next(c for c in grid["columns"] if c["title"] == "Einheit")
    assert unit_col["type"] == "dropdown"
    assert all(
        isinstance(item, dict) and item.get("id") and item.get("name")
        for item in unit_col["source"]
    )
    intent_col = next(c for c in grid["columns"] if c["title"] == "Vorgang")
    assert intent_col["source"][0] == {"id": "update", "name": "aktualisieren"}
    apply_edits(db_session, run, [{"row_id": row.id, "field": "rabatt_2", "value": "0"}])
    db_session.refresh(row)
    assert row.rabatt_2 == Decimal("0")
    apply_edits(
        db_session, run, [{"row_id": row.id, "field": "rabatt_1", "value": "100"}]
    )
    db_session.refresh(row)
    assert derived_prices(row, run)["ek"] == Decimal("0")


def _assert_san_fields_aligned(rows: list[SupplySourceRow]) -> None:
    groups: dict[str, list[SupplySourceRow]] = {}
    for row in rows:
        groups.setdefault(row.supplier_article_number, []).append(row)
    for members in groups.values():
        lead = members[0]
        for other in members[1:]:
            for field in SAN_FIELDS:
                left = getattr(lead, field)
                right = getattr(other, field)
                if field == "field_overrides":
                    assert dict(left or {}) == dict(right or {})
                else:
                    assert left == right, field


def test_locked_unit_edit_rejected(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.status = "preview"
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="LOCK-U",
        row_intent="update",
        unit_id="3566",
    )
    db_session.add(row)
    db_session.flush()
    with pytest.raises(SupplySourceRunError, match="weclapp lehnt das ab"):
        apply_edits(
            db_session,
            run,
            [{"row_id": row.id, "field": "unit_id", "value": "4259"}],
        )


def test_create_without_unit_blocks_approval(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.status = "preview"
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="NEW-PART",
        match_status="matched",
        row_intent="create",
        weclapp_article_id="a1",
        article_number="999.010.1010",
        unit_id=None,
        unit_raw="t",
    )
    set_rates(row, rabatt_1=Decimal(0), rabatt_2=Decimal(0), kein_rabatt=True)
    db_session.add(row)
    db_session.flush()
    assert approval_blockers([row])["create_no_unit"] == 1
    assert can_approve([row]) is False
    assert approval_blockers([row])["missing_unit_raws"] == ["t"]
    row.unit_id = "3566"
    db_session.flush()
    assert can_approve([row]) is True


def test_priceless_blocks_update_allows_create(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.status = "preview"
    create_row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="NEW-NO-PRICE",
        listenpreis=None,
        listenpreis_raw="auf Anfrage",
        match_status="matched",
        row_intent="create",
        weclapp_article_id="a1",
        article_number="999.010.4010",
        unit_id="3566",
    )
    set_rates(create_row, rabatt_1=Decimal(0), rabatt_2=Decimal(0), kein_rabatt=True)
    update_row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="UPD-NO-PRICE",
        listenpreis=None,
        listenpreis_raw="auf Anfrage",
        match_status="matched",
        row_intent="update",
        weclapp_article_id="a2",
        article_number="999.010.4011",
        weclapp_supply_source_id="ss-np",
        unit_id="3566",
    )
    set_rates(update_row, rabatt_1=Decimal(0), rabatt_2=Decimal(0), kein_rabatt=True)
    db_session.add_all([create_row, update_row])
    db_session.flush()
    assert can_approve([create_row]) is True
    assert approval_blockers([update_row])["priceless_price"] == 1
    assert can_approve([update_row]) is False
    from app.supply_source_runs import summary_counts

    counts = summary_counts([create_row, update_row])
    assert counts["priceless"] == 2
    assert counts["create"] == 0
    assert counts["update"] == 0


def test_assign_unit_flags_file_mirror_mismatch(db_session):
    from app.supply_source_resolve import resolve_row

    supplier = _supplier(db_session)
    _ss(db_session, ss_id="ss-unit-ow", san="OW-SAN")
    _article(db_session, aid="a-unit-ow", number="999.010.2010", code="A")
    _link(db_session, ss_id="ss-unit-ow", aid="a-unit-ow", number="999.010.2010")
    run = _run(db_session, supplier)
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="OW-SAN",
        unit_id="4259",
        file_unit_id="4259",
        unit_raw="lfm",
    )
    db_session.add(row)
    db_session.flush()
    resolve_row(db_session, run, row, supplier=supplier)
    db_session.flush()
    db_session.refresh(row)
    assert row.unit_id == "3566"
    assert row.file_unit_id == "4259"
    assert row.unit_raw == "lfm"
    assert row.unit_overwritten is True
    grid = build_grid_config(run, [row])
    assert 0 in grid["unitOverwriteRows"]
    assert "lfm" in (grid["unitOverwriteTitles"][0] or "")


def test_assign_currency_flag_when_live_code_differs(db_session):
    from app.supply_source_resolve import resolve_row

    supplier = _supplier(db_session)
    _ss(db_session, ss_id="ss-cur-ow", san="CUR-SAN", currency="CHF")
    _article(db_session, aid="a-cur-ow", number="999.010.3010", code="A")
    _link(db_session, ss_id="ss-cur-ow", aid="a-cur-ow", number="999.010.3010")
    run = _run(db_session, supplier)
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="CUR-SAN",
        listenpreis=Decimal("10"),
    )
    db_session.add(row)
    db_session.flush()
    resolve_row(db_session, run, row, supplier=supplier)
    db_session.flush()
    db_session.refresh(row)
    assert row.currency_overwritten is True
    assert (row.current_ek_currency or "").upper() == "CHF"
    grid = build_grid_config(run, [row])
    assert 0 in grid["currencyOverwriteRows"]
    assert "CHF" in (row.current_ek_currency or "")
    assert grid["currencyOverwriteTitles"][0]


def test_assign_unit_overwrite_survives_run_resolve_commit(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="ss-unit-ow-commit", san="OW-SAN-COMMIT")
    _article(db_session, aid="a-unit-ow-commit", number="999.010.2011", code="A")
    _link(
        db_session,
        ss_id="ss-unit-ow-commit",
        aid="a-unit-ow-commit",
        number="999.010.2011",
    )
    run = _run(db_session, supplier)
    run.source = "upload"
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="OW-SAN-COMMIT",
        unit_id="4259",
        file_unit_id="4259",
        unit_raw="lfm",
    )
    db_session.add(row)
    db_session.flush()
    row_id = row.id
    run_resolve(db_session, run, oid="x", skip_index=True)
    db_session.expire_all()
    fresh = db_session.get(SupplySourceRow, row_id)
    assert fresh is not None
    assert fresh.unit_id == "3566"
    assert fresh.file_unit_id == "4259"
    assert fresh.unit_raw == "lfm"
    assert fresh.unit_overwritten is True


def test_attach_without_unit_blocks_approval(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.status = "preview"
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="ATTACH-PART",
        match_status="matched",
        row_intent="attach",
        weclapp_article_id="a1",
        article_number="999.010.1010",
        unit_id=None,
    )
    set_rates(row, rabatt_1=Decimal(0), rabatt_2=Decimal(0), kein_rabatt=True)
    db_session.add(row)
    db_session.flush()
    assert approval_blockers([row])["attach_no_unit"] == 1
    assert can_approve([row]) is False


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
    with patch("app.jobs.enqueue") as enqueue:
        import uuid

        from app.models import Job

        job = Job(
            id=uuid.uuid4(),
            job_type="supply_source_apply",
            payload={"run_id": run.id, "chunk_index": 0},
            status="queued",
            created_by_oid="x",
            created_by_name="x",
        )
        db_session.add(job)
        db_session.flush()
        enqueue.return_value = job
        approve_run(db_session, run, {"oid": "x", "name": "Dennis"})
    db_session.refresh(run)
    assert run.status == "applying"
    assert run.approved_at is not None


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


def test_rate_edit_applies_to_whole_san_group(db_session):
    supplier = _supplier(db_session)
    _ss(db_session, ss_id="tst-ss-shared-rate", san="TST-RATE")
    _article(db_session, aid="tst-r1", number="999.030.0040")
    _article(db_session, aid="tst-r2", number="999.030.0070")
    _link(db_session, ss_id="tst-ss-shared-rate", aid="tst-r1", number="999.030.0040")
    _link(db_session, ss_id="tst-ss-shared-rate", aid="tst-r2", number="999.030.0070")
    run = _run(db_session, supplier)
    run_resolve(db_session, run, oid="x", skip_index=True)
    run.status = "preview"
    db_session.flush()
    rows = list(
        db_session.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        )
    )
    assert len(rows) == 2
    apply_edits(
        db_session,
        run,
        [{"row_id": rows[0].id, "field": "rabatt_1", "value": "10"}],
    )
    refreshed = list(
        db_session.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        )
    )
    assert all(r.discount_set for r in refreshed)
    assert all(r.rabatt_1 == Decimal("0.10") for r in refreshed)
    _assert_san_fields_aligned(refreshed)


def test_san_group_invariant_catches_skipped_sync(db_session):
    supplier = _supplier(db_session)
    run = _run(db_session, supplier)
    run.status = "preview"
    a = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="DRIFT",
        listenpreis=Decimal("10"),
        article_number="999.111.0001",
    )
    b = SupplySourceRow(
        run_id=run.id,
        supplier_article_number="DRIFT",
        listenpreis=Decimal("10"),
        article_number="999.111.0002",
    )
    db_session.add_all([a, b])
    db_session.flush()
    set_rates(a, rabatt_1=Decimal("0.50"), rabatt_2=Decimal("0"))
    db_session.flush()
    with pytest.raises(AssertionError):
        _assert_san_fields_aligned([a, b])
    from app.supply_source_runs import sync_san_group

    sync_san_group(db_session, a)
    _assert_san_fields_aligned([a, b])


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
    assert "Bezugsquellenregistrierung" in neu.text
    assert "Vorlage erzeugen" in neu.text
    assert 'href="/bezugsquellen/neu/vorlage.xlsx"' in neu.text
    assert "ss-upload-supplier-wrap" in neu.text
    assert "Datei prüfen" in neu.text
    xlsx = user_client.get("/bezugsquellen/neu/vorlage.xlsx")
    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers["content-type"]
    assert "bezugsquellen-vorlage.xlsx" in xlsx.headers["content-disposition"]
    home = user_client.get("/")
    assert home.status_code == 200
    assert "Bezugsquellenregistrierung" in home.text
    assert "Bezugsquellenexport" not in home.text
    assert 'href="/bezugsquellen/neu"' in home.text
    js = user_client.get("/static/supply_source_grid.js")
    assert js.status_code == 200
    assert b"kein_rabatt" in js.content
    assert b"filters: true" in js.content
    assert b"rabattcode" in js.content


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
    assert "built-in method" not in page.text
    assert "0 zu aktualisieren" not in page.text
    assert "0 nur Preisänderung" not in page.text
    assert "jspreadsheet_common.js" in page.text
    assert page.text.count("weclapp-Assistent-CSV herunterladen") == 2
    assert '"freezeColumns": 1' in page.text
    assert "Rabattsätze nach Rabattcode" in page.text
    assert "ss-bulk-code" in page.text
    assert "Auf Auswahl anwenden" not in page.text
    assert ("Artikelzuordnung übernehmen" in page.text) or (
        "Artikelzuordnung \\u00fcbernehmen" in page.text
    )
    assert "Alle sichtbaren Zeilen" not in page.text
    assert "ss-filter-code" not in page.text
    assert "Aufschlag (%)" in page.text
    assert 'id="ss-aufschlag"' in page.text
    assert 'type="date"' in page.text
    assert "datetime-local" not in page.text
    assert "0.5000" not in page.text
    assert 'id="ss-aufschlag"' in page.text
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
    assert body["ek_preview"]
    assert "TST-HTTP" in body["ek_preview"][0]
    with patch("app.jobs.enqueue") as enqueue:
        import uuid

        from app.models import Job

        job = Job(
            id=uuid.uuid4(),
            job_type="supply_source_apply",
            payload={"run_id": run.id, "chunk_index": 0},
            status="queued",
            created_by_oid="x",
            created_by_name="x",
        )
        db_session.add(job)
        db_session.flush()
        enqueue.return_value = job
        approve = user_client.post(
            f"/bezugsquellen/neu/{run.id}/freigeben",
            data={"preis_eintritt": "2026-09-07"},
            follow_redirects=False,
        )
    assert approve.status_code == 303
    db_session.refresh(run)
    assert run.status == "applying"
    assert run.approved_at is not None
    from zoneinfo import ZoneInfo

    local = run.preis_eintritt.astimezone(ZoneInfo("Europe/Zurich"))
    assert local.date().isoformat() == "2026-09-07"
    assert local.hour == 0
    assert local.minute == 0


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
