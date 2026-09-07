"""weclapp-wizard CSV for a Bezugsquellen resolve run.

Separate from the frozen /bezugsquellen ExportRow writer. Renders validated
SupplySourceRow values; does not call weclapp.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SupplySourceRow, SupplySourceRun, WeclappUnit
from app.supply_export_csv import format_decimal_comma
from app.supply_source_runs import SupplySourceRunError, ZURICH, format_preis_eintritt_input

DISCOUNT_PRICE_TYPE = "DISCOUNT_PCT"

WIZARD_CSV_HEADERS: tuple[str, ...] = (
    "ARTIKELNAME",
    "Handelssprache",
    "Lokaler Artikelname",
    "Lieferantenartikelnummer",
    "Lieferanten Firmenname",
    "LIEFERANTENNUMMER",
    "Bruttokaufpreis",
    "Zu- und Abschläge Bezeichnung 1",
    "Zu- und Abschläge Preisart 1",
    "Zu- und Abschläge Wert 1",
    "Zu- und Abschläge Bezeichnung 2",
    "Zu- und Abschläge Preisart 2",
    "Zu- und Abschläge Wert 2",
    "Währung",
    "Artikel-Mengeneinheit",
    "Matchcode",
    "Artikel aktiv",
    "Preis-Eintritt",
    "Warengruppen-Name",
    "Warengruppen Beschreibung",
    "Steuersatz",
    "Zugehörigen Verkaufsartikel erstellen oder aktualisieren",
    "Verkaufsartikel-Nummer",
    "Bruttopreis des zugehörigen Verkaufsartikels",
    "Verkaufsartikel-Währung",
    "Vertriebsweg",
    "Vertriebsweg-Steuersatz",
    "Kurztext 1",
    "Handelssprache",
    "Lokalisierte Kurztext 1",
    "Kurztext 2",
    "Handelssprache",
    "Lokalisierte Kurztext 2",
    "Artikelbeschreibung",
    "Handelssprache",
    "Lokalisierte Artikelbeschreibung",
    "Interner Hinweis",
    "Handelssprache",
    "Lokalisierter interner Hinweis",
    "Artikel-Langbeschreibung",
    "Handelssprache",
    "Lokalisierte Lange Artikelbeschreibung",
    "EAN-Nummer",
    "MPN-Nummer",
    "Artikeltyp",
    "Serienartikel",
    "Hersteller",
    "Bruttogewicht",
    "Nettogewicht",
    "Zolltarifnummer",
    "Länge Artikel",
    "Breite Artikel",
    "Höhe Artikel",
    "Herstellertyp",
    "Einführungsdatum",
    "Sicherheitstage",
    "Mindestlagerbestand",
    "Zielbestand",
    "Wiederbeschaffungstage",
    "Durchschnittliche Lieferzeit",
    "Mindestbestellmenge",
    "Gebindemenge",
    "Lieferantenbestand",
    "Dropshipping möglich",
    "In Dropshipping-Automatisierung ignorieren",
    "Kostenstelle Verkauf",
    "Kostenstelle Einkauf",
    "Kostenart",
    "Primäre Bezugsquelle",
)

assert len(WIZARD_CSV_HEADERS) == 69

_IDX = {name: i for i, name in enumerate(WIZARD_CSV_HEADERS)}
# Duplicate header "Handelssprache" keeps the first index; unused duplicates stay empty.


def csv_row_candidates(rows: Iterable[SupplySourceRow]) -> list[SupplySourceRow]:
    return [
        row
        for row in rows
        if row.included
        and row.row_intent != "skip"
        and row.match_status != "unmatched"
    ]


def format_percent_points(fraction: Decimal) -> str:
    """Stored discount fraction (0.5) → percent points for the wizard (50)."""
    points = (fraction * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if points == points.to_integral_value():
        return str(int(points))
    text = format(points, "f").rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _article_name(row: SupplySourceRow) -> str:
    overrides = row.field_overrides or {}
    if overrides.get("name") == "template":
        return (row.template_name or "").strip()
    return (row.name or "").strip()


def _eintritt_display(run: SupplySourceRun) -> str:
    iso = format_preis_eintritt_input(run.preis_eintritt)
    if not iso:
        return ""
    day = datetime.fromisoformat(iso).date()
    return day.strftime("%d.%m.%Y")


def _unit_names(db: Session, rows: list[SupplySourceRow]) -> dict[str, str]:
    ids = {str(row.unit_id).strip() for row in rows if str(row.unit_id or "").strip()}
    if not ids:
        return {}
    found = db.scalars(select(WeclappUnit).where(WeclappUnit.weclapp_id.in_(ids))).all()
    return {u.weclapp_id: (u.name or "").strip() for u in found}


def _missing_unit_error(rows: list[SupplySourceRow], names: dict[str, str]) -> str | None:
    lines: list[str] = []
    for row in rows:
        uid = str(row.unit_id or "").strip()
        name = names.get(uid, "") if uid else ""
        if uid and name:
            continue
        raw = (row.unit_raw or "").strip() or "(leer)"
        lines.append(f"{row.supplier_article_number} · {raw}")
    if not lines:
        return None
    listed = "\n".join(lines)
    return (
        "CSV nicht erzeugt: Einheit fehlt oder ist unbekannt "
        "(weclapp-Name, nicht der Dateitext). Betroffene Zeilen:\n"
        f"{listed}"
    )


def _discount_cells(row: SupplySourceRow) -> tuple[str, str, str, str]:
    """I, J, L, M. Empty when the corresponding rate is unset or the row is priceless."""
    if row.listenpreis is None or not row.discount_set:
        return "", "", "", ""
    i = j = l = m = ""
    if row.rabatt_1 is not None:
        i = DISCOUNT_PRICE_TYPE
        j = format_percent_points(Decimal(row.rabatt_1))
    if row.rabatt_2 is not None:
        l = DISCOUNT_PRICE_TYPE
        m = format_percent_points(Decimal(row.rabatt_2))
    return i, j, l, m


def _values_for_row(
    row: SupplySourceRow,
    run: SupplySourceRun,
    *,
    unit_name: str,
    supplier_number: str,
) -> list[str]:
    values = [""] * len(WIZARD_CSV_HEADERS)
    values[_IDX["ARTIKELNAME"]] = _article_name(row)
    values[_IDX["Lieferantenartikelnummer"]] = row.supplier_article_number or ""
    values[_IDX["LIEFERANTENNUMMER"]] = supplier_number
    if row.listenpreis is not None:
        values[_IDX["Bruttokaufpreis"]] = format_decimal_comma(Decimal(row.listenpreis))
        i, j, l, m = _discount_cells(row)
        values[_IDX["Zu- und Abschläge Preisart 1"]] = i
        values[_IDX["Zu- und Abschläge Wert 1"]] = j
        values[_IDX["Zu- und Abschläge Preisart 2"]] = l
        values[_IDX["Zu- und Abschläge Wert 2"]] = m
    values[_IDX["Währung"]] = (run.einkaufswaehrung or "").strip()
    values[_IDX["Artikel-Mengeneinheit"]] = unit_name
    values[_IDX["Preis-Eintritt"]] = _eintritt_display(run)
    values[_IDX["Verkaufsartikel-Nummer"]] = (row.article_number or "").strip()
    values[_IDX["Verkaufsartikel-Währung"]] = (run.verkaufswaehrung or "").strip()
    return values


def wizard_csv_filename(run: SupplySourceRun, *, when: datetime | None = None) -> str:
    supplier = ""
    if run.supplier is not None:
        supplier = (run.supplier.supplier_number or "").strip()
    stamp = when or datetime.now(ZURICH)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    day = stamp.astimezone(ZURICH).date().isoformat()
    return f"bezugsquellen-{supplier or 'lieferant'}-lauf-{run.id}-{day}.csv"


def render_wizard_csv(
    db: Session,
    run: SupplySourceRun,
    rows: list[SupplySourceRow],
) -> tuple[bytes, str]:
    selected = csv_row_candidates(rows)
    names = _unit_names(db, selected)
    missing = _missing_unit_error(selected, names)
    if missing:
        raise SupplySourceRunError(missing)

    supplier_number = ""
    if run.supplier is not None:
        supplier_number = (run.supplier.supplier_number or "").strip()

    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter=";",
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\r\n",
    )
    writer.writerow(list(WIZARD_CSV_HEADERS))
    for row in selected:
        uid = str(row.unit_id or "").strip()
        values = _values_for_row(
            row,
            run,
            unit_name=names[uid],
            supplier_number=supplier_number,
        )
        writer.writerow(values)
    payload = buffer.getvalue().encode("utf-8-sig")
    return payload, wizard_csv_filename(run)
