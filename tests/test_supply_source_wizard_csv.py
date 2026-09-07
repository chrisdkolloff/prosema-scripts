"""weclapp-wizard CSV for a Bezugsquellen resolve run."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.main import app
from app.models import Supplier, SupplySourceRow, SupplySourceRun, WeclappUnit
from app.supply_source_runs import SupplySourceRunError, derived_prices, set_rates
from app.supply_source_wizard_csv import (
    WIZARD_CSV_HEADERS,
    format_percent_points,
    render_wizard_csv,
)

PLAIN = {
    "oid": "oid-wizard-csv",
    "name": "Dennis",
    "email": "user@example.com",
    "roles": ["user"],
}

ZURICH = ZoneInfo("Europe/Zurich")

G = WIZARD_CSV_HEADERS.index("Bruttokaufpreis")
I = WIZARD_CSV_HEADERS.index("Zu- und Abschläge Preisart 1")
J = WIZARD_CSV_HEADERS.index("Zu- und Abschläge Wert 1")
L = WIZARD_CSV_HEADERS.index("Zu- und Abschläge Preisart 2")
M = WIZARD_CSV_HEADERS.index("Zu- und Abschläge Wert 2")
N = WIZARD_CSV_HEADERS.index("Währung")
O = WIZARD_CSV_HEADERS.index("Artikel-Mengeneinheit")
R = WIZARD_CSV_HEADERS.index("Preis-Eintritt")
V = WIZARD_CSV_HEADERS.index("Zugehörigen Verkaufsartikel erstellen oder aktualisieren")
W = WIZARD_CSV_HEADERS.index("Verkaufsartikel-Nummer")
X = WIZARD_CSV_HEADERS.index("Bruttopreis des zugehörigen Verkaufsartikels")
Y = WIZARD_CSV_HEADERS.index("Verkaufsartikel-Währung")
Z = WIZARD_CSV_HEADERS.index("Vertriebsweg")


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
        return PLAIN

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


def _unit(db: Session) -> None:
    if db.get(WeclappUnit, "3566") is None:
        db.add(
            WeclappUnit(
                weclapp_id="3566",
                name="Stk.",
                description="Stück",
                last_seen_at=datetime.now(UTC),
            )
        )
        db.flush()


def _supplier(db: Session) -> Supplier:
    row = db.scalars(select(Supplier).where(Supplier.supplier_number == "19996")).first()
    if row:
        return row
    row = Supplier(
        supplier_number="19996",
        weclapp_party_id="party-wizard-csv",
        name="Wizard-CSV-Test",
        einkaufswaehrung="EUR",
        default_kurs=Decimal("0.93"),
        default_aufschlag=Decimal("0.50"),
        default_verkaufswaehrung="CHF",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _run(db: Session) -> SupplySourceRun:
    supplier = _supplier(db)
    run = SupplySourceRun(
        supplier_id=supplier.id,
        status="preview",
        source="upload",
        einkaufswaehrung="EUR",
        kurs=Decimal("0.93"),
        verkaufswaehrung="CHF",
        aufschlag=Decimal("0.50"),
        preis_eintritt=datetime(2026, 9, 7, tzinfo=ZURICH),
        created_by=PLAIN["oid"],
        created_by_name=PLAIN["name"],
    )
    db.add(run)
    db.flush()
    run.supplier = supplier
    return run


def _row(db: Session, run: SupplySourceRun, *, san: str, **kwargs) -> SupplySourceRow:
    row = SupplySourceRow(
        run_id=run.id,
        supplier_article_number=san,
        name=kwargs.get("name", "Testartikel"),
        listenpreis=kwargs.get("listenpreis", Decimal("49.90")),
        match_status=kwargs.get("match_status", "matched"),
        row_intent=kwargs.get("row_intent", "price_only"),
        included=kwargs.get("included", True),
        unit_id=kwargs.get("unit_id", "3566"),
        unit_raw=kwargs.get("unit_raw", "Stk"),
        article_number=kwargs.get("article_number", "999.999.001"),
    )
    if kwargs.get("discount", True):
        set_rates(
            row,
            rabatt_1=kwargs.get("rabatt_1", Decimal("0.5")),
            rabatt_2=kwargs.get("rabatt_2", Decimal("0")),
        )
    db.add(row)
    db.flush()
    return row


def _parse(payload: bytes) -> list[list[str]]:
    text = payload.decode("utf-8-sig")
    return list(csv.reader(StringIO(text), delimiter=";"))


def test_headers_are_69_in_spec_order():
    assert len(WIZARD_CSV_HEADERS) == 69
    assert WIZARD_CSV_HEADERS[0] == "ARTIKELNAME"
    assert WIZARD_CSV_HEADERS[3] == "Lieferantenartikelnummer"
    assert WIZARD_CSV_HEADERS[5] == "LIEFERANTENNUMMER"
    assert WIZARD_CSV_HEADERS[6] == "Bruttokaufpreis"
    assert WIZARD_CSV_HEADERS[14] == "Artikel-Mengeneinheit"
    assert WIZARD_CSV_HEADERS[-1] == "Primäre Bezugsquelle"


def test_half_fraction_renders_as_integer_percent_points():
    assert format_percent_points(Decimal("0.5")) == "50"
    assert format_percent_points(Decimal("0.5")) != "0,5"
    assert "," not in format_percent_points(Decimal("0.5"))


def test_priced_and_priceless_and_filters(db_session):
    _unit(db_session)
    run = _run(db_session)
    priced = _row(db_session, run, san="SAN-PREIS")
    _row(
        db_session,
        run,
        san="SAN-OHNE",
        listenpreis=None,
        discount=False,
    )
    _row(db_session, run, san="SAN-SKIP", row_intent="skip")
    _row(db_session, run, san="SAN-UNMATCHED", match_status="unmatched")

    rows = list(
        db_session.scalars(
            select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
        )
    )
    payload, filename = render_wizard_csv(db_session, run, rows)
    assert payload.startswith(b"\xef\xbb\xbf")
    assert filename.startswith("bezugsquellen-19996-lauf-")
    assert filename.endswith(".csv")

    table = _parse(payload)
    assert table[0] == list(WIZARD_CSV_HEADERS)
    assert len(table[0]) == 69
    body = table[1:]
    sans = [r[3] for r in body]
    assert sans == ["SAN-OHNE", "SAN-PREIS"] or set(sans) == {"SAN-OHNE", "SAN-PREIS"}
    assert "SAN-SKIP" not in sans
    assert "SAN-UNMATCHED" not in sans

    priced_line = next(r for r in body if r[3] == "SAN-PREIS")
    priceless_line = next(r for r in body if r[3] == "SAN-OHNE")
    assert len(priced_line) == 69
    assert priced_line[G] == "49,90"
    assert priced_line[J] == "50"
    assert priced_line[I] == "DISCOUNT_PCT"
    assert priced_line[L] == "DISCOUNT_PCT"
    assert priced_line[M] == "0"
    assert priced_line[N] == "EUR"
    assert priced_line[O] == "Stk."
    assert priced_line[R] == "07.09.2026"
    assert priced_line[V] == ""
    assert priced_line[W] == "999.999.001"
    assert priced_line[X] == ""
    assert priced_line[Y] == "CHF"
    assert priced_line[N] != priced_line[Y]
    assert priced_line[Z] == ""

    ek = derived_prices(priced, run)["ek"]
    assert ek == Decimal("24.95")
    assert "24,95" not in priced_line
    assert priced_line[G] != "24,95"
    for cell in priced_line:
        assert cell != "24.95"
        assert cell != "24,95"

    assert priceless_line[G] == ""
    assert priceless_line[I] == ""
    assert priceless_line[J] == ""
    assert priceless_line[L] == ""
    assert priceless_line[M] == ""


def test_missing_unit_refuses_entire_file(db_session):
    _unit(db_session)
    run = _run(db_session)
    good = _row(db_session, run, san="SAN-OK")
    bad = _row(
        db_session,
        run,
        san="SAN-NO-UNIT",
        unit_id=None,
        unit_raw="Karton",
    )
    with pytest.raises(SupplySourceRunError) as exc:
        render_wizard_csv(db_session, run, [good, bad])
    assert "SAN-NO-UNIT" in str(exc.value)
    assert "Karton" in str(exc.value)
    assert "CSV nicht erzeugt" in str(exc.value)


def test_http_download_bom_and_detail_buttons(user_client, db_session):
    _unit(db_session)
    run = _run(db_session)
    _row(db_session, run, san="SAN-HTTP")
    page = user_client.get(f"/bezugsquellen/neu/{run.id}")
    assert page.status_code == 200
    assert page.text.count("weclapp-Assistent-CSV herunterladen") == 2
    assert f"/bezugsquellen/neu/{run.id}/weclapp.csv" in page.text

    response = user_client.get(f"/bezugsquellen/neu/{run.id}/weclapp.csv")
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "text/csv" in response.headers["content-type"]
    table = _parse(response.content)
    assert table[1][G] == "49,90"
    assert table[1][J] == "50"
    assert table[1][N] == "EUR"
    assert table[1][Y] == "CHF"


def test_purchase_and_sales_currencies_are_independent(db_session):
    _unit(db_session)
    run = _run(db_session)
    run.einkaufswaehrung = "EUR"
    run.verkaufswaehrung = "CHF"
    _row(db_session, run, san="SAN-CUR")
    payload, _ = render_wizard_csv(
        db_session,
        run,
        list(
            db_session.scalars(
                select(SupplySourceRow).where(SupplySourceRow.run_id == run.id)
            )
        ),
    )
    line = _parse(payload)[1]
    assert line[N] == "EUR"
    assert line[Y] == "CHF"
    assert line[N] != line[Y]


def test_http_missing_unit_redirects_without_csv(user_client, db_session):
    run = _run(db_session)
    _row(db_session, run, san="SAN-FAIL", unit_id=None, unit_raw="lfm")
    response = user_client.get(
        f"/bezugsquellen/neu/{run.id}/weclapp.csv",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert response.content == b"" or b"ARTIKELNAME" not in response.content
