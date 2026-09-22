"""Rombro accounting export from weclapp-shaped transactions."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.accounting_rombro_export import (
    ROMBRO_COLUMNS,
    date_to_ms,
    export_rombro_csv,
    fetch_accounting_transactions,
    format_rombro_date,
    parse_export_date,
    transaction_to_rombro_rows,
    write_rombro_csv,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "accounting"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


LEDGER = {
    "acc-debit-1411": "1411",
    "acc-credit-904": "904",
    "acc-debit-153": "153",
    "acc-credit-3200": "3200",
}

CURRENCY = {"265": "CHF"}


def test_parse_export_date_and_range():
    assert parse_export_date("2026-01-15", label="Von") == date(2026, 1, 15)
    with pytest.raises(ValueError, match="Von-Datum"):
        parse_export_date("", label="Von-Datum")
    assert date_to_ms(date(2026, 1, 1)) < date_to_ms(date(2026, 1, 1), end_of_day=True)


def test_incoming_two_line_pairing():
    txn = _load("incoming_two_line.json")
    warnings: list[str] = []
    rows = transaction_to_rombro_rows(
        txn,
        ledger_lookup=LEDGER,
        currency_lookup=CURRENCY,
        warnings=warnings,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["Belegnummer"] == "Mietkaution Prosema // Gretzenbach"
    assert row["Soll"] == "1411"
    assert row["Haben"] == "904"
    assert row["Betrag"] == "7500"
    assert row["Währung"] == "CHF"
    assert row["Wechselkurs"] == ""
    assert row["MWST Code"] == ""
    assert format_rombro_date(txn["transactionDate"]) == row["Datum"]


def test_incoming_one_credit_multiple_debits():
    txn = _load("incoming_three_line.json")
    ledger = {
        "acc-debit-expense": "6570",
        "acc-debit-vat": "1170",
        "acc-credit-vendor": "915",
    }
    rows = transaction_to_rombro_rows(
        txn,
        ledger_lookup=ledger,
        currency_lookup=CURRENCY,
        warnings=[],
    )
    assert len(rows) == 2
    amounts = sorted(Decimal(r["Betrag"]) for r in rows)
    assert amounts == [Decimal("28.45"), Decimal("351.1")]
    assert all(r["Haben"] == "915" for r in rows)


def test_outgoing_one_debit_multiple_credits():
    txn = _load("outgoing_three_line.json")
    rows = transaction_to_rombro_rows(
        txn,
        ledger_lookup=LEDGER,
        currency_lookup=CURRENCY,
        warnings=[],
    )
    assert len(rows) == 2
    assert all(r["Belegnummer"] == "RE1009" for r in rows)
    assert all(r["Soll"] == "153" for r in rows)
    assert all(r["Haben"] == "3200" for r in rows)
    amounts = sorted(Decimal(r["Betrag"]) for r in rows)
    assert amounts == [Decimal("81"), Decimal("1000")]


def test_multi_multi_skipped_with_warning():
    txn = _load("incoming_multi_multi.json")
    warnings: list[str] = []
    rows = transaction_to_rombro_rows(
        txn,
        ledger_lookup={"acc-debit-a": "1", "acc-credit": "2"},
        currency_lookup=CURRENCY,
        warnings=warnings,
    )
    assert rows == []
    assert any("mehrere Soll- und Haben" in w for w in warnings)


def test_missing_external_record_number_skipped():
    txn = _load("incoming_two_line.json")
    txn = dict(txn)
    txn["externalRecordNumber"] = ""
    warnings: list[str] = []
    assert (
        transaction_to_rombro_rows(
            txn,
            ledger_lookup=LEDGER,
            currency_lookup=CURRENCY,
            warnings=warnings,
        )
        == []
    )
    assert any("externalRecordNumber" in w for w in warnings)


class _FakeClient:
    def __init__(self, transactions: list[dict]):
        self._transactions = transactions

    def iter_pages(self, entity: str, *, params=None, page_size=None):
        if entity == "accountingTransaction":
            rows = self._transactions
            if params:
                lo = params.get("transactionDate-ge")
                hi = params.get("transactionDate-le")
                if lo is not None:
                    rows = [r for r in rows if r["transactionDate"] >= lo]
                if hi is not None:
                    rows = [r for r in rows if r["transactionDate"] <= hi]
            yield from rows
            return
        if entity == "ledgerAccount":
            for aid, num in LEDGER.items():
                yield {"id": aid, "accountNumber": num}
            return
        if entity == "currency":
            yield {"id": "265", "name": "CHF"}
            return
        raise AssertionError(entity)


def test_fetch_filters_storno_and_drafts():
    txns = [
        {
            "transactionDate": 1789509600000,
            "reverseTransaction": True,
            "draft": False,
            "status": "ESTABLISHED",
        },
        {
            "transactionDate": 1789509600000,
            "reverseTransaction": False,
            "draft": True,
            "status": "DRAFT",
        },
    ]
    client = _FakeClient(txns)
    all_rows = fetch_accounting_transactions(
        client,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        include_storno=True,
        include_drafts=True,
    )
    assert len(all_rows) == 2

    no_storno = fetch_accounting_transactions(
        client,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        include_storno=False,
        include_drafts=True,
    )
    assert len(no_storno) == 1

    no_drafts = fetch_accounting_transactions(
        client,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        include_storno=True,
        include_drafts=False,
    )
    assert len(no_drafts) == 1
    assert no_drafts[0]["status"] == "ESTABLISHED"


def test_write_rombro_csv_header(tmp_path: Path):
    path = tmp_path / "out.csv"
    write_rombro_csv(
        path,
        [
            {
                "Belegnummer": "RE1009",
                "Datum": "15.09.2026",
                "Beschreibung": "Test",
                "Betrag": "100",
                "Währung": "CHF",
                "Wechselkurs": "",
                "Soll": "153",
                "Haben": "3200",
                "MWST Code": "",
                "MWST Konto": "",
            }
        ],
    )
    text = path.read_text(encoding="utf-8")
    assert text.startswith(",".join(ROMBRO_COLUMNS))
    assert "RE1009" in text


def test_export_rombro_csv_integration(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.accounting_rombro_export.EXPORT_DIR",
        tmp_path,
    )
    client = _FakeClient([_load("incoming_two_line.json")])
    path, stats = export_rombro_csv(
        client,
        artifact_id=__import__("uuid").uuid4(),
        date_from=date(2020, 1, 1),
        date_to=date(2030, 12, 31),
        include_storno=True,
        include_drafts=True,
    )
    assert path.is_file()
    assert stats.rows_written == 1
    assert stats.transactions_seen == 1
