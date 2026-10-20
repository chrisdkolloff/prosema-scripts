"""Live catalogue, first-use settings and selection validation (no live writes)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.main import app
from app.models import Supplier, SuppliersAudit
from app.supply_source_runs import SupplySourceRunError
from app.supply_source_suppliers import resolve_supplier, supplier_catalogue
from scripts.weclapp.client import WeclappError

USER = {"oid": "supplier-picker-test", "name": "Test", "roles": ["user"]}
PARTY = {
    "id": "999001",
    "supplierNumber": "19996",
    "company": "Testbedarf AG",
    "supplier": True,
    "supplierActive": True,
}


@pytest.fixture
def db_session():
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def local(db):
    return db.scalar(select(Supplier).where(Supplier.supplier_number == "10000"))


def test_catalogue_reads_all_pages_and_does_not_create_suppliers(db_session):
    supplier = local(db_session)
    fake = Mock()
    fake.iter_pages.return_value = iter(
        [
            {**PARTY, "id": supplier.weclapp_party_id, "supplierNumber": "10000"},
            PARTY,
            {**PARTY, "id": "999002", "supplierActive": False},
            {**PARTY, "id": "999003", "supplier": False},
        ]
    )
    before = db_session.scalar(select(func.count()).select_from(Supplier))
    with patch("app.supply_source_suppliers.weclapp_client_for", return_value=fake):
        result = supplier_catalogue(db_session, USER["oid"])
    assert [(r["id"], r["needs_setup"]) for r in result] == [
        (str(supplier.id), False),
        ("weclapp:999001", True),
    ]
    assert db_session.scalar(select(func.count()).select_from(Supplier)) == before
    assert fake.iter_pages.call_args.kwargs["params"]["supplier-eq"] == "true"


@pytest.mark.parametrize("deleted", [False, True])
def test_catalogue_does_not_reactivate_local_suppliers(db_session, deleted):
    supplier = local(db_session)
    if deleted:
        supplier.deleted_at = datetime.now(UTC)
    else:
        supplier.is_active = False
    fake = Mock()
    fake.iter_pages.return_value = iter([{**PARTY, "id": supplier.weclapp_party_id}])
    with patch("app.supply_source_suppliers.weclapp_client_for", return_value=fake):
        assert supplier_catalogue(db_session, USER["oid"]) == []


def test_new_supplier_uses_confirmed_settings_and_audit(db_session):
    fake = Mock()
    fake.get.return_value = PARTY
    with patch("app.supply_source_suppliers.weclapp_client_for", return_value=fake):
        supplier = resolve_supplier(
            db_session,
            selection="weclapp:999001",
            user=USER,
            currency="EUR",
            rate="0,94",
            markup="35,25",
        )
    assert supplier.supplier_number == "19996"
    assert supplier.default_kurs == Decimal("0.94")
    assert supplier.default_aufschlag == Decimal("0.3525")
    assert supplier.default_verkaufswaehrung == "CHF"
    audit = db_session.scalar(select(SuppliersAudit).where(SuppliersAudit.entity_id == supplier.id))
    assert audit.action == "created"
    assert audit.actor_oid == USER["oid"]
    fake.post.assert_not_called()
    fake.put.assert_not_called()


@pytest.mark.parametrize(
    "currency,rate,markup",
    [
        ("", "1", "50"),
        ("EUR", "", "50"),
        ("EUR", "1", ""),
        ("EUR", "0", "50"),
        ("EUR", "NaN", "50"),
        ("EUR", "Infinity", "50"),
        ("EUR", "1", "NaN"),
        ("EUR", "1", "Infinity"),
        ("EUR", "1", "-1"),
        ("CHF", "0.93", "50"),
        ("EUR", "0.0000001", "50"),
        ("EUR", "1", "0.001"),
    ],
)
def test_new_supplier_requires_valid_explicit_settings(db_session, currency, rate, markup):
    with patch("app.supply_source_suppliers.weclapp_client_for") as factory:
        with pytest.raises(SupplySourceRunError):
            resolve_supplier(
                db_session,
                selection="weclapp:999001",
                user=USER,
                currency=currency,
                rate=rate,
                markup=markup,
            )
        factory.assert_not_called()


def test_existing_supplier_keeps_settings_and_needs_no_live_access(db_session):
    supplier = local(db_session)
    before = (supplier.default_kurs, supplier.default_aufschlag, supplier.einkaufswaehrung)
    with patch("app.supply_source_suppliers.weclapp_client_for") as factory:
        for selection in (str(supplier.id), f"weclapp:{supplier.weclapp_party_id}"):
            assert (
                resolve_supplier(
                    db_session, selection=selection, user=USER, currency="CHF", rate="1", markup="0"
                ).id
                == supplier.id
            )
        factory.assert_not_called()
    assert before == (supplier.default_kurs, supplier.default_aufschlag, supplier.einkaufswaehrung)


@pytest.mark.parametrize(
    "party",
    [{**PARTY, "supplierActive": False}, {**PARTY, "supplier": False}, {**PARTY, "id": "123"}],
)
def test_remote_identity_and_active_status_are_checked(db_session, party):
    fake = Mock()
    fake.get.return_value = party
    with (
        patch("app.supply_source_suppliers.weclapp_client_for", return_value=fake),
        pytest.raises(SupplySourceRunError),
    ):
        resolve_supplier(
            db_session,
            selection="weclapp:999001",
            user=USER,
            currency="CHF",
            rate="1",
            markup="0",
        )
    assert db_session.scalar(select(Supplier).where(Supplier.weclapp_party_id == "999001")) is None


def test_supplier_page_has_shared_visible_search_and_no_default(client):
    page = client.get("/bezugsquellen/neu")
    assert page.status_code == 200
    assert 'id="ss-upload-supplier-wrap" class=' in page.text
    assert 'id="ss-selected-supplier" value=""' in page.text
    assert 'formaction="/bezugsquellen/neu/abfragen"' in page.text
    assert 'id="ss-supplier-setup"' in page.text


def test_catalogue_access_failure_is_clear_and_not_cached(client):
    fake = Mock()
    fake.iter_pages.side_effect = WeclappError("Forbidden", status_code=403)
    with patch("app.supply_source_suppliers.weclapp_client_for", return_value=fake):
        response = client.get("/bezugsquellen/neu/lieferanten")
    assert response.status_code == 400
    assert "Lizenz" in response.json()["error"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["abfragen", "upload"])
def test_both_actions_use_the_selected_supplier(client, db_session, path):
    supplier = local(db_session)
    function = "create_pull_run" if path == "abfragen" else "create_upload_run"
    kwargs = {"data": {"supplier_id": str(supplier.id)}, "follow_redirects": False}
    if path == "upload":
        kwargs["files"] = {"datei": ("prices.csv", b"test", "text/csv")}
    with patch(
        f"app.routes.supply_source_runs.{function}", return_value=SimpleNamespace(id=123)
    ) as create:
        response = client.post(f"/bezugsquellen/neu/{path}", **kwargs)
    assert response.status_code == 303
    assert create.call_args.kwargs["supplier_id"] == supplier.id


def test_free_text_does_not_start_a_run(client):
    with patch("app.routes.supply_source_runs.create_pull_run") as create:
        response = client.post(
            "/bezugsquellen/neu/abfragen", data={"supplier_id": "DURAL"}, follow_redirects=False
        )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    create.assert_not_called()


@pytest.mark.parametrize("path", ["abfragen", "upload"])
def test_first_use_settings_are_used_by_both_actions(client, db_session, path):
    fake = Mock()
    fake.get.return_value = PARTY
    function = "create_pull_run" if path == "abfragen" else "create_upload_run"
    kwargs = {
        "data": {
            "supplier_id": "weclapp:999001",
            "supplier_currency": "EUR",
            "supplier_rate": "0.94",
            "supplier_markup": "35",
        },
        "follow_redirects": False,
    }
    if path == "upload":
        kwargs["files"] = {"datei": ("prices.csv", b"test", "text/csv")}
    with (
        patch("app.supply_source_suppliers.weclapp_client_for", return_value=fake),
        patch(
            f"app.routes.supply_source_runs.{function}", return_value=SimpleNamespace(id=123)
        ) as create,
    ):
        response = client.post(f"/bezugsquellen/neu/{path}", **kwargs)
    assert response.status_code == 303
    supplier = db_session.get(Supplier, create.call_args.kwargs["supplier_id"])
    assert supplier.default_kurs == Decimal("0.94")
    assert supplier.default_aufschlag == Decimal("0.35")
    assert supplier.einkaufswaehrung == "EUR"
    fake.post.assert_not_called()
    fake.put.assert_not_called()


def test_supplier_number_collision_is_rejected_without_overwriting(db_session):
    fake = Mock()
    fake.get.return_value = {**PARTY, "supplierNumber": "10000"}
    supplier = local(db_session)
    before = (supplier.weclapp_party_id, supplier.name, supplier.default_aufschlag)
    with (
        patch("app.supply_source_suppliers.weclapp_client_for", return_value=fake),
        pytest.raises(SupplySourceRunError, match="anders zugeordnet"),
    ):
        resolve_supplier(
            db_session, selection="weclapp:999001", user=USER, currency="CHF", rate="1", markup="35"
        )
    assert before == (supplier.weclapp_party_id, supplier.name, supplier.default_aufschlag)
