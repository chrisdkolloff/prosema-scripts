"""Bezugsquellenexport: discounts, validation, CSV archive."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.main import app
from app.models import DiscountCategory, ExportRow, ExportRun
from app.supply_export_csv import build_csv_row, serialise_export_csv
from app.supply_exports import (
    ARTICLE_NUMBER_FIELD,
    apply_row_patch,
    article_number_column_width,
    assert_run_editable,
    build_columns,
    build_grid_config,
    current_discount_categories,
    pull_export_rows,
    validate_and_preview,
)
from scripts.export.generate_weclapp_import import DISCOUNT_PRICE_TYPE, read_template_headers
from scripts.paths import PROJECT_ROOT

PLAIN_USER = {
    "oid": "user-oid-supply",
    "name": "Christopher Kolloff",
    "email": "user@example.com",
    "roles": ["user"],
}

TEMPLATE = (
    PROJECT_ROOT
    / "data"
    / "SupplySourcesWeclapp DemoImportfile_de (28.10.2024)(1).csv"
)


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
        app.dependency_overrides.clear()


def _ensure_dural_categories(db_session: Session) -> dict[str, DiscountCategory]:
    existing = current_discount_categories(db_session, "10000")
    if existing:
        return existing
    row = DiscountCategory(
        supplier_id="10000",
        category_code="A",
        label="Fliesenprofile",
        base_discount_pct=Decimal("50"),
        customer_discount_pct=Decimal("50"),
        source="test",
        valid_from=date(2026, 1, 1),
        recorded_by="test",
    )
    db_session.add(row)
    db_session.flush()
    return current_discount_categories(db_session, "10000")


def _make_run(
    db_session: Session,
    *,
    status: str = "draft",
    price_entry_date: date | None = date(2026, 8, 25),
    sales_article_currency: str = "EUR",
) -> ExportRun:
    run = ExportRun(
        id=uuid.uuid4(),
        status=status,
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
        supplier_id="10000",
        row_count=0,
        included_count=0,
        price_entry_date=price_entry_date,
        sales_article_currency=sales_article_currency,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _add_row(
    db_session: Session,
    run: ExportRun,
    *,
    article_number: str = "010.020.0010",
    supplier_article: str = "D-100",
    category: str = "A",
    intent: str = "apply",
    included: bool = False,
    d1: str = "50",
    d2: str = "50",
    override_reason: str | None = None,
    ek: str = "10.00",
) -> ExportRow:
    cats = _ensure_dural_categories(db_session)
    cat = cats.get(category)
    row = ExportRow(
        id=uuid.uuid4(),
        run_id=run.id,
        position=run.row_count or 0,
        article_number=article_number,
        supplier_article_number=supplier_article,
        supplier_number="10000",
        article_name=f"Artikel {article_number}",
        ek_price_before_discount=Decimal(ek),
        unit="Stk.",
        matchcode="MC",
        discount_category=category if intent != "zero" else "",
        discount_category_id=cat.id if cat and intent == "apply" else None,
        base_discount_pct=Decimal(d1),
        customer_discount_pct=Decimal(d2),
        discount_intent=intent,
        row_intent="update",
        included=included,
        override_reason=override_reason,
        weclapp_supply_source_id=f"ss-{supplier_article}",
        weclapp_current_ek=Decimal(ek),
        weclapp_current_is_primary=True,
        extras={},
        article_context={},
        dropshipping_possible=True,
        weclapp_current_dropshipping=True,
    )
    db_session.add(row)
    run.row_count = (run.row_count or 0) + 1
    if included:
        run.included_count = (run.included_count or 0) + 1
    db_session.flush()
    return row


def test_list_page(user_client):
    response = user_client.get("/bezugsquellen")
    assert response.status_code == 200
    assert "Bezugsquellenexport" in response.text
    assert "Neue Abfrage starten" in response.text


def test_detail_uses_jspreadsheet_grid(user_client, db_session):
    run = _make_run(db_session)
    _add_row(db_session, run, included=False)
    db_session.commit()
    response = user_client.get(f"/bezugsquellen/{run.id}")
    assert response.status_code == 200
    assert 'id="supply-spreadsheet"' in response.text
    assert "supply_export_grid.js" in response.text
    assert "supply-grid-config" in response.text
    assert "supply-column-picker" in response.text
    assert "Pflichtfelder" in response.text
    assert "Arbeitsspalten" in response.text
    assert "Bezugsquelle (optional)" in response.text
    assert "Artikel (nur Anzeige)" in response.text
    assert "ek_price_before_discount" in response.text
    assert "discount_intent" not in response.text
    assert "Rabatt-Intent" not in response.text
    assert "Einbeziehen" not in response.text
    assert "— kein Rabatt —" in response.text
    assert "Import-Einstellungen" in response.text
    assert 'name="price_entry_date"' in response.text
    assert 'name="sales_article_currency"' in response.text


def test_edits_endpoint_updates_and_recalculates(user_client, db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=False, ek="10.00", d1="50", d2="50")
    # Match weclapp discounts so only EK / name edits drive change detection.
    row.weclapp_current_base_discount_pct = Decimal("50")
    row.weclapp_current_customer_discount_pct = Decimal("50")
    db_session.commit()
    response = user_client.post(
        f"/bezugsquellen/{run.id}/edits",
        json=[
            {"row_id": str(row.id), "field": "ek_price_before_discount", "value": "20.00"},
            {"row_id": str(row.id), "field": "matchcode", "value": "NEU-MC"},
        ],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["rows"]) == 1
    values = data["rows"][0]["values"]
    assert data["rows"][0]["changed"] is True
    assert "included" not in values
    assert "discount_intent" not in values
    assert values["matchcode"] == "NEU-MC"
    assert values["ek_price_before_discount"] == "20.00"
    assert values["ek_after"] == "5.00"  # 20 * 0.5 * 0.5
    db_session.refresh(row)
    assert row.included is True  # matchcode edit sets dirty flag
    assert row.matchcode == "NEU-MC"


def test_unchanged_rows_not_exported_changed_rows_are(db_session):
    from app.supply_exports import row_has_changes

    run = _make_run(db_session)
    changed = _add_row(db_session, run, supplier_article="IN", included=True)
    unchanged = _add_row(
        db_session,
        run,
        supplier_article="OUT",
        included=False,
        article_number="010.020.0020",
    )
    unchanged.weclapp_current_base_discount_pct = Decimal("50")
    unchanged.weclapp_current_customer_discount_pct = Decimal("50")
    db_session.flush()
    assert row_has_changes(changed) is True
    assert row_has_changes(unchanged) is False
    rows = [r for r in (changed, unchanged) if row_has_changes(r)]
    payload = serialise_export_csv(db_session, run, rows, template_path=TEMPLATE)
    text = payload.decode("cp1252", errors="replace")
    assert "IN" in text
    assert "OUT" not in text


def test_csv_quotes_inch_mark_and_semicolons(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    row.article_name = 'WSWM 1, 2" Tropfenschutzmanschette'
    row.matchcode = "A;B"
    db_session.flush()
    payload = serialise_export_csv(db_session, run, [row], template_path=TEMPLATE)
    text = payload.decode("cp1252")
    assert '"WSWM 1, 2"" Tropfenschutzmanschette"' in text
    assert '"A;B"' in text
    parsed = csv.reader(io.StringIO(text), delimiter=";")
    headers = next(parsed)
    values = next(parsed)
    assert values[headers.index("ARTIKELNAME")] == 'WSWM 1, 2" Tropfenschutzmanschette'
    assert values[headers.index("Matchcode")] == "A;B"


def test_unresolved_blocks_download(db_session):
    run = _make_run(db_session)
    _add_row(
        db_session,
        run,
        included=True,
        intent="unresolved",
        category="",
        d1="0",
        d2="0",
    )
    report = validate_and_preview(db_session, run)
    assert any(e.code == "unresolved_discount" for e in report.errors)


def test_explicit_zero_writes_discount_pct_zero(db_session):
    run = _make_run(db_session)
    row = _add_row(
        db_session,
        run,
        included=True,
        intent="zero",
        category="",
        d1="0",
        d2="0",
        override_reason="Manuell entfernt",
    )
    headers, *_ = read_template_headers(TEMPLATE)
    registry = current_discount_categories(db_session, "10000")
    data = build_csv_row(headers, row, registry)
    assert data["Zu- und Abschläge Preisart 1"] == DISCOUNT_PRICE_TYPE
    assert data["Zu- und Abschläge Wert 1"] == "0"
    assert data["Zu- und Abschläge Preisart 2"] == DISCOUNT_PRICE_TYPE
    assert data["Zu- und Abschläge Wert 2"] == "0"
    assert "Rabatt entfernt" in data["Zu- und Abschläge Bezeichnung 1"]
    assert data["Verkaufsartikel-Nummer"] == row.article_number
    assert data["Bruttopreis des zugehörigen Verkaufsartikels"] == ""
    assert data["Verkaufsartikel-Währung"] == "EUR"
    assert data["Preis-Eintritt"] == "25.08.2026"
    assert data["Zugehörigen Verkaufsartikel erstellen oder aktualisieren"] == ""
    assert data["Primäre Bezugsquelle"] == "ja"
    assert data["Dropshipping möglich"] == "ja"


def test_missing_run_settings_block_preview_and_are_not_invented(db_session):
    run = _make_run(db_session, price_entry_date=None, sales_article_currency="")
    row = _add_row(db_session, run, included=True)
    report = validate_and_preview(db_session, run)
    codes = {e.code for e in report.errors}
    assert "missing_price_entry_date" in codes
    assert "missing_sales_article_currency" in codes
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(
        headers, row, current_discount_categories(db_session, "10000"), run=run
    )
    assert data["Preis-Eintritt"] == ""
    assert data["Verkaufsartikel-Währung"] == ""


def test_run_settings_saved_from_editor(user_client, db_session):
    run = _make_run(db_session, price_entry_date=None, sales_article_currency="")
    row = _add_row(db_session, run, included=True)
    db_session.commit()
    response = user_client.post(
        f"/bezugsquellen/{run.id}/einstellungen",
        data={
            "price_entry_date": "2026-08-01",
            "sales_article_currency": "chf",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(run)
    assert run.price_entry_date == date(2026, 8, 1)
    assert run.sales_article_currency == "CHF"
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(
        headers, row, current_discount_categories(db_session, "10000"), run=run
    )
    assert data["Preis-Eintritt"] == "01.08.2026"
    assert data["Verkaufsartikel-Währung"] == "CHF"


def test_exported_run_rejects_settings(user_client, db_session):
    run = _make_run(db_session, status="exported")
    db_session.commit()
    response = user_client.post(
        f"/bezugsquellen/{run.id}/einstellungen",
        data={
            "price_entry_date": "2026-08-01",
            "sales_article_currency": "CHF",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_override_requires_reason(db_session):
    run = _make_run(db_session)
    _add_row(
        db_session,
        run,
        included=True,
        intent="apply",
        d1="40",
        d2="50",
        override_reason=None,
    )
    report = validate_and_preview(db_session, run)
    assert any(e.code == "override_without_reason" for e in report.errors)

    run2 = _make_run(db_session)
    _add_row(
        db_session,
        run2,
        included=True,
        intent="apply",
        d1="40",
        d2="50",
        override_reason="Sonderkondition",
        supplier_article="X2",
        article_number="010.020.0099",
    )
    report2 = validate_and_preview(db_session, run2)
    assert not any(e.code == "override_without_reason" for e in report2.errors)


def test_missing_supplier_article_blocks(db_session):
    run = _make_run(db_session)
    _add_row(
        db_session,
        run,
        included=True,
        supplier_article="",
    )
    report = validate_and_preview(db_session, run)
    assert any(e.code == "missing_supplier_article_number" for e in report.errors)


def test_primary_flag_round_trips_nein(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    row.weclapp_current_is_primary = False
    db_session.flush()
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(headers, row, current_discount_categories(db_session, "10000"))
    assert data["Primäre Bezugsquelle"] == "nein"


def test_exported_run_rejects_edits(db_session):
    run = _make_run(db_session, status="exported")
    row = _add_row(db_session, run, included=True)
    with pytest.raises(ValueError, match="schreibgeschützt"):
        assert_run_editable(run)
    with pytest.raises(ValueError):
        apply_row_patch(
            db_session,
            run,
            row,
            {"matchcode": "X"},
            current_discount_categories(db_session, "10000"),
        )


def test_highlight_only_for_overrides_not_weclapp_diffs(db_session):
    from app.supply_exports import row_has_changes, row_is_highlighted

    run = _make_run(db_session)
    # Category A is 50/50; weclapp has 50/40 → export change, but not an override.
    row = _add_row(db_session, run, included=False, d1="50", d2="50")
    row.weclapp_current_base_discount_pct = Decimal("50")
    row.weclapp_current_customer_discount_pct = Decimal("40")
    db_session.flush()
    registry = current_discount_categories(db_session, "10000")
    assert row_has_changes(row) is True
    assert row_is_highlighted(row, registry) is False

    row.customer_discount_pct = Decimal("45")  # override vs category 50
    db_session.flush()
    assert row_is_highlighted(row, registry) is True


def test_zero_category_label_sets_intent_zero(db_session):
    from app.supply_exports import ZERO_CATEGORY_LABEL, row_has_changes

    run = _make_run(db_session)
    row = _add_row(db_session, run, included=False, d1="50", d2="50")
    row.weclapp_current_base_discount_pct = Decimal("50")
    row.weclapp_current_customer_discount_pct = Decimal("50")
    db_session.flush()
    apply_row_patch(
        db_session,
        run,
        row,
        {"discount_category": ZERO_CATEGORY_LABEL},
        current_discount_categories(db_session, "10000"),
    )
    assert row.discount_intent == "zero"
    assert row.base_discount_pct == Decimal("0")
    assert row_has_changes(row) is True


def test_download_archives_and_is_byte_identical(user_client, db_session):
    run = _make_run(db_session)
    _add_row(db_session, run, included=True)
    db_session.commit()

    first = user_client.post(f"/bezugsquellen/{run.id}/download")
    assert first.status_code == 200
    assert first.headers["content-type"].startswith("text/csv")
    body1 = first.content
    assert DISCOUNT_PRICE_TYPE.encode() in body1
    assert b"DISCOUNT_PCT" in body1

    db_session.refresh(run)
    assert run.status == "exported"
    assert run.file == body1

    second = user_client.post(f"/bezugsquellen/{run.id}/download")
    assert second.status_code == 200
    assert second.content == body1


def test_pull_one_row_per_supply_source(db_session):
    run = _make_run(db_session, status="running")
    _ensure_dural_categories(db_session)

    article = {
        "id": "a1",
        "articleNumber": "010.020.0010",
        "name": "Profil",
        "matchCode": "MC",
        "unitId": "u1",
        "articleCategoryId": "c1",
        "primarySupplySourceId": "ss1",
        "supplySources": [
            {"articleSupplySourceId": "ss1"},
            {"articleSupplySourceId": "ss2"},
        ],
        "customAttributes": [
            {"attributeDefinitionId": "attr-rabatt", "stringValue": "A"},
        ],
    }
    lookups = MagicMock()
    lookups.attribute_labels = {"attr-rabatt": "Rabattcode"}
    lookups.supply_sources = {
        "ss1": {
            "id": "ss1",
            "articleNumber": "D-1",
            "supplierId": "p1",
            "unitId": "u1",
            "articlePrices": [{"price": "10.00"}],
        },
        "ss2": {
            "id": "ss2",
            "articleNumber": "D-2",
            "supplierId": "p1",
            "unitId": "u1",
            "articlePrices": [{"price": "12.00"}],
        },
        "ss-other": {
            "id": "ss-other",
            "articleNumber": "X",
            "supplierId": "p2",
            "articlePrices": [{"price": "1"}],
        },
    }
    lookups.supply_source.side_effect = lambda sid: lookups.supply_sources.get(sid, {})
    lookups.party.side_effect = lambda pid: (
        {"supplierNumber": "10000", "company": "DURAL"}
        if pid == "p1"
        else {"supplierNumber": "99999"}
    )
    lookups.category_names.return_value = ("Holz - 010", "Bretter - 020")
    lookups.unit_name.return_value = "Stk."

    client = MagicMock()
    client.iter_pages.return_value = [article]

    with (
        patch("app.weclapp.weclapp_client_for", return_value=client),
        patch("app.supply_exports.build_lookups", return_value=lookups),
    ):
        result = pull_export_rows(db_session, run, oid=PLAIN_USER["oid"])

    assert result["row_count"] == 2
    rows = list(db_session.scalars(select(ExportRow).where(ExportRow.run_id == run.id)))
    assert {r.supplier_article_number for r in rows} == {"D-1", "D-2"}
    assert all(r.row_intent == "update" for r in rows)
    assert all(r.included is False for r in rows)
    assert all(r.discount_intent == "apply" for r in rows)


def test_grid_article_number_is_first_frozen_column():
    numbers = ["010.020.0010", "999.888.7777"]
    assert article_number_column_width(numbers) >= 110
    columns = build_columns({}, editable=True, article_numbers=numbers)
    assert columns[0]["name"] == ARTICLE_NUMBER_FIELD
    assert columns[0]["title"] == "Artikelnr."
    assert columns[0]["width"] >= 110
    assert columns[0]["readOnly"] is True
    assert columns[1]["name"] == "article_name"


def test_grid_config_freezes_article_number_and_name(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run)
    config = build_grid_config(run, [row], current_discount_categories(db_session, "10000"))
    assert config["freezeColumns"] == 2
    assert config["fields"][0] == ARTICLE_NUMBER_FIELD
    assert config["fields"][1] == "article_name"
    assert config["columns"][0]["width"] >= 110
    assert config["data"][0][0] == row.article_number


def test_empty_discount_columns_never_on_exported_row(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(headers, row, current_discount_categories(db_session, "10000"))
    assert data["Zu- und Abschläge Preisart 1"]
    assert data["Zu- und Abschläge Wert 1"]
    assert data["Zu- und Abschläge Preisart 2"]
    assert data["Zu- und Abschläge Wert 2"]


def test_catalog_covers_template_headers():
    from app.supply_export_fields import BY_COLUMN, FIELDS, column_letter_index

    headers, *_ = read_template_headers(TEMPLATE)
    for index, header in enumerate(headers):
        letter = None
        for spec in FIELDS:
            if spec.label_weclapp == header and column_letter_index(spec.weclapp_column) == index:
                letter = spec.weclapp_column
                break
        assert letter, f"no catalog field for template column {index} {header!r}"
        assert BY_COLUMN[letter].label_weclapp == header


def test_identity_and_preisart_not_editable_or_in_picker():
    from app.supply_export_fields import BY_KEY, editable_keys, picker_fields

    for key in ("article_name", "unit", "supplier_article_number", "supplier_number"):
        assert BY_KEY[key].edit_policy == "read_only"
        assert key not in editable_keys()
        assert BY_KEY[key].picker_group == "identity"
        assert BY_KEY[key].hideable is False
    assert "disc1_type" not in {spec.field_key for spec in picker_fields()}
    assert "disc2_type" not in {spec.field_key for spec in picker_fields()}
    assert BY_KEY["ean"].edit_policy == "read_only"
    assert BY_KEY["ean"].write_policy == "locked"


def test_hidden_optional_value_still_exports(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    row.extras = {"target_stock": "12"}
    db_session.flush()
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(headers, row, current_discount_categories(db_session, "10000"))
    assert data["Zielbestand"] == "12,00"


def test_empty_optional_column_absent_from_csv(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(headers, row, current_discount_categories(db_session, "10000"))
    assert data["Zielbestand"] == ""
    assert data["Mindestlagerbestand"] == ""
    assert data["Verkaufsartikel-Nummer"] == row.article_number
    assert data["EAN-Nummer"] == ""


def test_locked_column_value_fails_gate(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    row.extras = {"ean": "4001234567890"}
    db_session.flush()
    report = validate_and_preview(db_session, run)
    assert any(e.code == "locked_column_value" for e in report.errors)


def test_article_context_does_not_export_or_fail_gate(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    row.article_context = {"ean": "4001234567890", "short_text_1": "Kurz"}
    db_session.flush()
    report = validate_and_preview(db_session, run)
    assert not any(e.code == "locked_column_value" for e in report.errors)
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(headers, row, current_discount_categories(db_session, "10000"))
    assert data["EAN-Nummer"] == ""
    assert data["Kurztext 1"] == ""


def test_written_columns_preview_lists_zielbestand(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True)
    row.extras = {"target_stock": "12"}
    db_session.flush()
    report = validate_and_preview(db_session, run)
    by_key = {col.field_key: col for col in report.written_columns}
    assert "target_stock" in by_key
    assert by_key["target_stock"].non_empty_count == 1
    assert by_key["target_stock"].weclapp_column == "BF"
    assert "ean" not in by_key
    assert by_key["sales_article_number"].weclapp_column == "W"
    assert by_key["sales_article_number"].non_empty_count == 1
    assert by_key["price_entry"].weclapp_column == "R"
    assert by_key["sales_currency"].weclapp_column == "Y"


def test_visibility_pref_not_stored_on_run(user_client, db_session):
    from app.models import UserPreference
    from app.supply_export_fields import TOOL_KEY, preset_keys

    run = _make_run(db_session)
    _add_row(db_session, run)
    db_session.commit()
    response = user_client.post(
        "/bezugsquellen/spalten",
        json={"preset": "mandatory"},
    )
    assert response.status_code == 200, response.text
    visible = response.json()["visible"]
    assert visible == list(preset_keys("mandatory"))
    assert "article_number" not in visible
    assert "article_name" in visible
    db_session.refresh(run)
    assert "visible" not in (run.filter_json or {})
    pref = db_session.get(
        UserPreference, {"user_oid": PLAIN_USER["oid"], "tool_key": TOOL_KEY}
    )
    assert pref is not None
    assert pref.pref_json["visible"] == visible


def test_article_name_not_editable_via_edits(user_client, db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run)
    db_session.commit()
    response = user_client.post(
        f"/bezugsquellen/{run.id}/edits",
        json=[{"row_id": str(row.id), "field": "article_name", "value": "Hack"}],
    )
    assert response.status_code == 400
    db_session.refresh(row)
    assert row.article_name == f"Artikel {row.article_number}"


def test_sales_article_number_always_written_from_article_number(db_session):
    from app.supply_export_fields import BY_KEY

    assert BY_KEY["sales_article_number"].write_policy == "always"
    assert BY_KEY["create_sales_article"].write_policy == "locked"
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True, article_number="010.020.0010")
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(
        headers, row, current_discount_categories(db_session, "10000"), run=run
    )
    assert data["Verkaufsartikel-Nummer"] == "010.020.0010"
    payload = serialise_export_csv(db_session, run, [row], template_path=TEMPLATE)
    text = payload.decode("cp1252")
    parsed = csv.reader(io.StringIO(text), delimiter=";")
    headers_out = next(parsed)
    values = next(parsed)
    assert values[headers_out.index("Verkaufsartikel-Nummer")] == "010.020.0010"


def test_empty_sales_article_number_raises_in_serialiser(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True, article_number="")
    with pytest.raises(ValueError, match="Verkaufsartikel-Nummer"):
        serialise_export_csv(db_session, run, [row], template_path=TEMPLATE)


def test_malformed_article_number_blocks_download(db_session):
    run = _make_run(db_session)
    _add_row(db_session, run, included=True, article_number="09018030")
    report = validate_and_preview(db_session, run)
    assert any(e.code == "malformed_article_number" for e in report.errors)


def test_missing_article_number_blocks_and_flags_empty_w(db_session):
    run = _make_run(db_session)
    _add_row(db_session, run, included=True, article_number="")
    report = validate_and_preview(db_session, run)
    codes = {e.code for e in report.errors}
    assert "missing_article_number" in codes
    assert "empty_sales_article_number" in codes


def test_price_entry_date_required_when_w_is_populated(db_session):
    run = _make_run(db_session, price_entry_date=None)
    _add_row(db_session, run, included=True)
    report = validate_and_preview(db_session, run)
    assert any(e.code == "missing_price_entry_date" for e in report.errors)


def test_three_digit_running_article_number_is_accepted(db_session):
    run = _make_run(db_session)
    row = _add_row(db_session, run, included=True, article_number="999.999.001")
    report = validate_and_preview(db_session, run)
    assert not any(
        e.code in {"malformed_article_number", "missing_article_number"}
        for e in report.errors
    )
    headers, *_ = read_template_headers(TEMPLATE)
    data = build_csv_row(
        headers, row, current_discount_categories(db_session, "10000"), run=run
    )
    assert data["Verkaufsartikel-Nummer"] == "999.999.001"


def test_supply_source_under_two_article_numbers_trips_duplicate_check(db_session):
    run = _make_run(db_session)
    _add_row(
        db_session,
        run,
        included=False,
        article_number="010.020.0010",
        supplier_article="D-SHARED",
    )
    _add_row(
        db_session,
        run,
        included=False,
        article_number="010.020.0020",
        supplier_article="D-SHARED",
    )
    report = validate_and_preview(db_session, run)
    assert any(e.code == "duplicate_match_key" for e in report.errors)


def test_pull_shared_supply_source_materialises_two_rows(db_session):
    run = _make_run(db_session, status="running")
    _ensure_dural_categories(db_session)

    real = {
        "id": "a-real",
        "articleNumber": "010.020.0010",
        "name": "Echt",
        "matchCode": "MC",
        "unitId": "u1",
        "articleCategoryId": "c1",
        "primarySupplySourceId": "ss1",
        "supplySources": [{"articleSupplySourceId": "ss1"}],
        "customAttributes": [
            {"attributeDefinitionId": "attr-rabatt", "stringValue": "A"},
        ],
    }
    junk = {
        "id": "a-junk",
        "articleNumber": "09018030",
        "name": "Junk",
        "matchCode": "MC",
        "unitId": "u1",
        "articleCategoryId": "c1",
        "primarySupplySourceId": "ss1",
        "supplySources": [{"articleSupplySourceId": "ss1"}],
        "customAttributes": [
            {"attributeDefinitionId": "attr-rabatt", "stringValue": "A"},
        ],
    }
    lookups = MagicMock()
    lookups.attribute_labels = {"attr-rabatt": "Rabattcode"}
    lookups.supply_sources = {
        "ss1": {
            "id": "ss1",
            "articleNumber": "09018030",
            "supplierId": "p1",
            "unitId": "u1",
            "articlePrices": [{"price": "10.00"}],
        },
    }
    lookups.supply_source.side_effect = lambda sid: lookups.supply_sources.get(sid, {})
    lookups.party.side_effect = lambda pid: {"supplierNumber": "10000", "company": "DURAL"}
    lookups.category_names.return_value = ("Holz - 010", "Bretter - 020")
    lookups.unit_name.return_value = "Stk."

    client = MagicMock()
    client.iter_pages.return_value = [real, junk]

    with (
        patch("app.weclapp.weclapp_client_for", return_value=client),
        patch("app.supply_exports.build_lookups", return_value=lookups),
    ):
        result = pull_export_rows(db_session, run, oid=PLAIN_USER["oid"])

    assert result["row_count"] == 2
    rows = list(db_session.scalars(select(ExportRow).where(ExportRow.run_id == run.id)))
    assert {r.article_number for r in rows} == {"010.020.0010", "09018030"}
    assert {r.supplier_article_number for r in rows} == {"09018030"}
    report = validate_and_preview(db_session, run)
    assert any(e.code == "duplicate_match_key" for e in report.errors)


def test_create_export_pull_defaults_eur_and_no_price_entry_date(db_session):
    from app.models import Job
    from app.supply_exports import DEFAULT_SALES_CURRENCY, create_export_pull

    job = Job(
        job_type="weclapp_supply_source_export",
        payload={},
        status="queued",
        created_by_oid=PLAIN_USER["oid"],
        created_by_name=PLAIN_USER["name"],
    )
    db_session.add(job)
    db_session.flush()
    with (
        patch("app.supply_exports.running_export", return_value=None),
        patch("app.jobs.enqueue", return_value=job),
    ):
        run = create_export_pull(db_session, PLAIN_USER)
    assert run.price_entry_date is None
    assert run.sales_article_currency == DEFAULT_SALES_CURRENCY == "EUR"


def test_run_settings_reject_empty_price_entry_date(user_client, db_session):
    run = _make_run(db_session, price_entry_date=None, sales_article_currency="EUR")
    db_session.commit()
    response = user_client.post(
        f"/bezugsquellen/{run.id}/einstellungen",
        data={"price_entry_date": "", "sales_article_currency": "EUR"},
        follow_redirects=False,
    )
    assert response.status_code == 400

