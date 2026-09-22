"""Export weclapp accounting transactions to Rombro CSV (Treuhand)."""

from __future__ import annotations

import csv
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.paths import DATA_DIR
from scripts.weclapp.client import WeclappClient

logger = logging.getLogger(__name__)

ZURICH = ZoneInfo("Europe/Zurich")

ROMBRO_COLUMNS = (
    "Belegnummer",
    "Datum",
    "Beschreibung",
    "Betrag",
    "Währung",
    "Wechselkurs",
    "Soll",
    "Haben",
    "MWST Code",
    "MWST Konto",
)

EXPORT_DIR = DATA_DIR / "accounting_exports"


@dataclass
class ExportStats:
    rows_written: int = 0
    transactions_seen: int = 0
    transactions_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary_message(self) -> str:
        parts = [
            f"{self.rows_written} Zeilen exportiert",
            f"({self.transactions_seen} Buchungen gelesen",
        ]
        if self.transactions_skipped:
            parts.append(f", {self.transactions_skipped} übersprungen")
        parts.append(").")
        if self.warnings:
            parts.append(f" {len(self.warnings)} Hinweise.")
        return "".join(parts)


def parse_export_date(raw: str, *, label: str) -> date:
    text = (raw or "").strip()
    if not text:
        raise ValueError(f"{label} fehlt.")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} ist kein gültiges Datum (JJJJ-MM-TT).") from exc


def date_to_ms(value: date, *, end_of_day: bool = False) -> int:
    if end_of_day:
        dt = datetime.combine(value, time(23, 59, 59, 999000), tzinfo=ZURICH)
    else:
        dt = datetime.combine(value, time.min, tzinfo=ZURICH)
    return int(dt.timestamp() * 1000)


def format_rombro_date(transaction_date_ms: int) -> str:
    dt = datetime.fromtimestamp(transaction_date_ms / 1000, tz=ZURICH)
    return dt.strftime("%d.%m.%Y")


def _parse_amount(raw: object) -> Decimal:
    if isinstance(raw, Decimal):
        return raw
    text = str(raw or "").strip()
    if not text:
        raise InvalidOperation(text)
    return Decimal(text)


def format_rombro_amount(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(int(normalized))
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def build_ledger_lookup(client: WeclappClient) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in client.iter_pages("ledgerAccount", params={"pageSize": 1000}):
        account_id = str(row.get("id") or "")
        number = str(row.get("accountNumber") or "").strip()
        if account_id and number:
            lookup[account_id] = number
    return lookup


def build_currency_lookup(client: WeclappClient) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in client.iter_pages("currency", params={"pageSize": 200}):
        currency_id = str(row.get("id") or "")
        code = str(row.get("name") or row.get("currencySymbol") or "").strip()
        if currency_id and code:
            lookup[currency_id] = code
    return lookup


def fetch_accounting_transactions(
    client: WeclappClient,
    *,
    date_from: date,
    date_to: date,
    include_storno: bool,
    include_drafts: bool,
) -> list[dict[str, Any]]:
    if date_from > date_to:
        raise ValueError("Das Von-Datum darf nicht nach dem Bis-Datum liegen.")

    params: dict[str, Any] = {
        "pageSize": 1000,
        "sort": "transactionDate",
        "transactionDate-ge": date_to_ms(date_from),
        "transactionDate-le": date_to_ms(date_to, end_of_day=True),
    }
    rows = list(client.iter_pages("accountingTransaction", params=params))

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not include_storno and row.get("reverseTransaction"):
            continue
        if not include_drafts:
            if row.get("draft") or row.get("status") == "DRAFT":
                continue
        filtered.append(row)
    return filtered


def _account_number(account_id: str, lookup: dict[str, str], warnings: list[str], ctx: str) -> str:
    number = lookup.get(account_id)
    if not number:
        warnings.append(f"{ctx}: Kontonummer für ledgerAccount {account_id} unbekannt.")
        return ""
    return number


def _split_details(
    details: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    debits = [d for d in details if d.get("debitCredit") == "DEBIT"]
    credits = [d for d in details if d.get("debitCredit") == "CREDIT"]
    return debits, credits


def _detail_amount(detail: dict[str, Any]) -> Decimal:
    return _parse_amount(detail.get("amount"))


def transaction_to_rombro_rows(
    transaction: dict[str, Any],
    *,
    ledger_lookup: dict[str, str],
    currency_lookup: dict[str, str],
    warnings: list[str],
) -> list[dict[str, str]]:
    details = list(transaction.get("transactionDetails") or [])
    if not details:
        ref = _belegnummer(transaction)
        warnings.append(f"Buchung {ref or transaction.get('id')}: keine Buchungszeilen.")
        return []

    debits, credits = _split_details(details)
    if not debits or not credits:
        ref = _belegnummer(transaction)
        warnings.append(f"Buchung {ref or transaction.get('id')}: unvollständige Soll/Haben-Zeilen.")
        return []

    belegnummer = _belegnummer(transaction)
    if not belegnummer:
        warnings.append(
            f"Buchung {transaction.get('transactionNumber') or transaction.get('id')}: "
            "externalRecordNumber fehlt — übersprungen."
        )
        return []

    datum = format_rombro_date(int(transaction["transactionDate"]))
    currency_code = currency_lookup.get(str(transaction.get("currencyId") or ""), "CHF")
    wechselkurs = _format_conversion_rate(transaction, currency_code)
    base = {
        "Belegnummer": belegnummer,
        "Datum": datum,
        "Währung": currency_code,
        "Wechselkurs": wechselkurs,
        "MWST Code": "",
        "MWST Konto": "",
    }

    ctx = f"Buchung {belegnummer}"

    if len(debits) == 1 and len(credits) == 1:
        debit, credit = debits[0], credits[0]
        if _detail_amount(debit) != _detail_amount(credit):
            warnings.append(f"{ctx}: Soll- und Haben-Betrag weichen ab — trotzdem exportiert.")
        return [
            _row_from_pair(
                base,
                debit,
                credit,
                ledger_lookup,
                warnings,
                ctx,
                amount_side="debit",
            )
        ]

    if len(debits) == 1 and len(credits) > 1:
        debit = debits[0]
        debit_total = _detail_amount(debit)
        credit_total = sum(_detail_amount(c) for c in credits)
        if debit_total != credit_total:
            warnings.append(
                f"{ctx}: Summe Haben ({credit_total}) ≠ Soll ({debit_total}) — Zeilen einzeln exportiert."
            )
        return [
            _row_from_pair(
                base,
                debit,
                credit,
                ledger_lookup,
                warnings,
                ctx,
                amount_side="credit",
            )
            for credit in credits
        ]

    if len(credits) == 1 and len(debits) > 1:
        credit = credits[0]
        debit_total = sum(_detail_amount(d) for d in debits)
        credit_total = _detail_amount(credit)
        if debit_total != credit_total:
            warnings.append(
                f"{ctx}: Summe Soll ({debit_total}) ≠ Haben ({credit_total}) — Zeilen einzeln exportiert."
            )
        return [
            _row_from_pair(
                base,
                debit,
                credit,
                ledger_lookup,
                warnings,
                ctx,
                amount_side="debit",
            )
            for debit in debits
        ]

    warnings.append(
        f"{ctx}: mehrere Soll- und Haben-Zeilen — nicht automatisch zuordenbar, übersprungen."
    )
    return []


def _belegnummer(transaction: dict[str, Any]) -> str:
    return str(transaction.get("externalRecordNumber") or "").strip()


def _format_conversion_rate(transaction: dict[str, Any], currency_code: str) -> str:
    if currency_code.upper() == "CHF":
        return ""
    raw = transaction.get("conversionRate")
    if raw in (None, "", "1", "1.0"):
        return ""
    return str(raw).strip()


def _row_from_pair(
    base: dict[str, str],
    debit: dict[str, Any],
    credit: dict[str, Any],
    ledger_lookup: dict[str, str],
    warnings: list[str],
    ctx: str,
    *,
    amount_side: str = "credit",
) -> dict[str, str]:
    soll = _account_number(str(debit.get("accountId") or ""), ledger_lookup, warnings, ctx)
    haben = _account_number(str(credit.get("accountId") or ""), ledger_lookup, warnings, ctx)
    description = str(debit.get("description") or credit.get("description") or "").strip()
    source = debit if amount_side == "debit" else credit
    amount = format_rombro_amount(_detail_amount(source))
    return {
        **base,
        "Beschreibung": description,
        "Betrag": amount,
        "Soll": soll,
        "Haben": haben,
    }


def write_rombro_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROMBRO_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in ROMBRO_COLUMNS})


def export_rombro_csv(
    client: WeclappClient,
    *,
    artifact_id: uuid.UUID,
    date_from: date,
    date_to: date,
    include_storno: bool,
    include_drafts: bool,
) -> tuple[Path, ExportStats]:
    stats = ExportStats()
    ledger_lookup = build_ledger_lookup(client)
    currency_lookup = build_currency_lookup(client)

    transactions = fetch_accounting_transactions(
        client,
        date_from=date_from,
        date_to=date_to,
        include_storno=include_storno,
        include_drafts=include_drafts,
    )
    stats.transactions_seen = len(transactions)

    out_rows: list[dict[str, str]] = []
    for transaction in transactions:
        rows = transaction_to_rombro_rows(
            transaction,
            ledger_lookup=ledger_lookup,
            currency_lookup=currency_lookup,
            warnings=stats.warnings,
        )
        if not rows:
            stats.transactions_skipped += 1
        out_rows.extend(rows)

    stats.rows_written = len(out_rows)
    path = EXPORT_DIR / f"{artifact_id}.csv"
    write_rombro_csv(path, out_rows)
    return path, stats


def run_export_job(
    client: WeclappClient,
    payload: dict[str, Any],
) -> dict[str, Any]:
    artifact_id = uuid.UUID(str(payload["artifact_id"]))
    date_from = parse_export_date(str(payload["date_from"]), label="Von-Datum")
    date_to = parse_export_date(str(payload["date_to"]), label="Bis-Datum")
    include_storno = bool(payload.get("include_storno"))
    include_drafts = bool(payload.get("include_drafts"))

    path, stats = export_rombro_csv(
        client,
        artifact_id=artifact_id,
        date_from=date_from,
        date_to=date_to,
        include_storno=include_storno,
        include_drafts=include_drafts,
    )

    if stats.rows_written == 0 and stats.transactions_seen > 0 and not stats.warnings:
        stats.warnings.append("Keine exportierbaren Zeilen — prüfen Sie Zeitraum und Filter.")

    logger.info(
        "rombro export artifact=%s rows=%s transactions=%s skipped=%s warnings=%s",
        artifact_id,
        stats.rows_written,
        stats.transactions_seen,
        stats.transactions_skipped,
        len(stats.warnings),
    )

    return {
        "message": stats.summary_message(),
        "artifact_id": str(artifact_id),
        "filename": path.name,
        "row_count": stats.rows_written,
        "transactions_seen": stats.transactions_seen,
        "transactions_skipped": stats.transactions_skipped,
        "warnings": stats.warnings[:50],
        "warning_count": len(stats.warnings),
    }
