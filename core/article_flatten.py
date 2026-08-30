"""Flatten weclapp articles for immutable snapshots (shared with export pipeline)."""

from __future__ import annotations

import re
from typing import Any

from core.article_payload import (
    ARTICLE_NAME_FIELD,
    ARTICLE_NUMBER_FIELD,
    LONG_TEXT_FIELD,
    get_row_value,
)
from scripts.weclapp.article_import import IMPORT_COLUMNS
from scripts.weclapp.master_columns import (
    EXPORT_COLUMNS,
    article_to_master_row,
    build_lookups,
)

_LABEL_RE = re.compile(r"^(.*?)\s*-\s*(\d{3})\s*$")

# Master/export column -> import-template column
_MASTER_TO_IMPORT: dict[str, str] = {
    "Prosema Artikelnummer": ARTICLE_NUMBER_FIELD,
    "Artikelnr.": "Lieferantenartikelnummer",
    "Hauptgruppe": "Hauptgruppe",
    "Untergruppe": "Untergruppe",
    "PROSEMA Kurztext": ARTICLE_NAME_FIELD,
    "PROSEMA Langtext": LONG_TEXT_FIELD,
    "Referenz (Matchcode)": "Referenz (Matchcode)",
    "GTIN (EAN-Nummer)": "GTIN (EAN-Nummer)",
    "Basiseinheitencode": "Einheit",
    "Kategorie": "Kategorie",
    "Grundmaterial": "Grundmaterial",
    "Oberfläche": "Oberfläche",
    "Farbe": "Farbe",
    "Produktfamilie": "Produktfamilie",
    "Rabattkategorie_Lieferant": "Rabattcode",
    "Verkaufseinheit": "Verkaufseinheit",
    "Verpackung": "Verpackung",
    "VPE 1": "VPE 1",
    "VPE 2": "VPE 2",
    "VPE 3": "VPE 3",
    "Breite mm": "Breite in mm",
    "Länge cm": "Länge in cm",
    "Höhe mm": "Höhe in mm",
    "Nettogewicht kg": "Nettogewicht kg",
    "Beschreibung": "Artikelbeschreibung HTML",
    "weclapp Kurzbeschreibung": "Kurzbeschreibung",
    "weclapp Artikeltyp": "Artikeltyp",
    "weclapp Aktiv": "Aktiv",
    "weclapp Im Verkauf": "Im Verkauf",
    "weclapp Steuersatz": "Steuersatz",
    "weclapp Im Shop verfügbar (Prosema)": "Im Shop verfügbar",
    "weclapp Im Shop aktiv (Prosema)": "Im Shop aktiv",
    "weclapp Bestand übertragen (Prosema)": "Bestand übertragen",
    "weclapp Gewichtseinheit": "Gewichtseinheit",
    "weclapp Produkt-ID (Prosema)": "Produkt-ID (Prosema)",
    "weclapp Varianten-ID (Prosema)": "Varianten-ID (Prosema)",
}

_DEFAULT_WIDTH = 140

_COLUMN_WIDTHS: dict[str, int] = {
    ARTICLE_NUMBER_FIELD: 160,
    "Prosema Artikelnummer": 160,
    "Lieferantenartikelnummer": 180,
    "Hauptgruppe": 190,
    "Untergruppe": 210,
    ARTICLE_NAME_FIELD: 220,
    "PROSEMA Kurztext": 220,
    LONG_TEXT_FIELD: 280,
    "PROSEMA Langtext": 280,
    "Kurzbeschreibung": 200,
    "Referenz (Matchcode)": 160,
    "GTIN (EAN-Nummer)": 150,
    "Artikeltyp": 120,
    "Einheit": 90,
    "Kategorie": 180,
    "Aktiv": 80,
    "Im Verkauf": 100,
    "Steuersatz": 120,
    "Im Shop verfügbar": 140,
    "Im Shop aktiv": 120,
    "Bestand übertragen": 150,
    "Gewichtseinheit": 130,
    "Grundmaterial": 140,
    "Oberfläche": 130,
    "Farbe": 110,
    "Produktfamilie": 140,
    "Rabattcode": 110,
    "Verkaufseinheit": 130,
    "Verpackung": 120,
    "VPE 1": 80,
    "VPE 2": 80,
    "VPE 3": 80,
    "Breite in mm": 110,
    "Länge in cm": 110,
    "Höhe in mm": 100,
    "Bodenleger": 110,
    "Dachdecker": 120,
    "Landschaftsgärtner": 150,
    "Plattenleger": 120,
    "Artikelbeschreibung HTML": 210,
    "Nettogewicht kg": 130,
    "Produkt-ID (Prosema)": 160,
    "Varianten-ID (Prosema)": 160,
    "Einkaufspreis EUR netto": 150,
    "Verkaufspreis €, BE": 140,
    "Einkaufspreis Prosema": 150,
    "Verkaufspreis": 130,
    "weclapp Artikel-ID": 140,
}


def _split_group_label(text: str) -> tuple[str, str]:
    cleaned = str(text or "").strip()
    match = _LABEL_RE.match(cleaned)
    if match:
        return match.group(1).strip(), match.group(2)
    return cleaned, cleaned


def _parse_active(value: str) -> bool:
    return str(value or "").strip().casefold() in {"ja", "true", "1", "yes"}


def master_row_to_snapshot_data(master_row: dict[str, str]) -> dict[str, str]:
    """Map a master-list row to import-template keys plus remaining export columns."""
    data: dict[str, str] = {column: "" for column in IMPORT_COLUMNS}
    for master_key, import_key in _MASTER_TO_IMPORT.items():
        value = master_row.get(master_key, "")
        if value and not data.get(import_key):
            data[import_key] = value

    extras: dict[str, str] = {}
    for key, value in master_row.items():
        if key in _MASTER_TO_IMPORT:
            continue
        if key in IMPORT_COLUMNS:
            if value and not data.get(key):
                data[key] = value
            continue
        if value:
            extras[key] = value

    data.update(extras)
    return data


def extract_indexed_fields(
    data: dict[str, str],
    *,
    weclapp_id: str = "",
    weclapp_version: str | None = None,
) -> dict[str, Any]:
    haupt_label = data.get("Hauptgruppe", "")
    unter_label = data.get("Untergruppe", "")
    _, haupt_code = _split_group_label(haupt_label)
    _, unter_code = _split_group_label(unter_label)
    active = _parse_active(data.get("Aktiv", ""))
    return {
        "article_number": get_row_value(data, ARTICLE_NUMBER_FIELD),
        "article_name": get_row_value(data, ARTICLE_NAME_FIELD),
        "hauptgruppe_code": haupt_code or haupt_label,
        "untergruppe_code": unter_code or unter_label,
        "active": active,
        "weclapp_id": weclapp_id or data.get("weclapp Artikel-ID", "") or "",
        "weclapp_version": weclapp_version,
    }


def build_snapshot_columns(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Ordered column list: import template first, then extras alphabetically."""
    present: set[str] = set()
    for row in rows:
        present.update(key for key, value in row.items() if value != "")

    ordered_keys: list[str] = list(IMPORT_COLUMNS)
    for key in sorted(present):
        if key not in ordered_keys:
            ordered_keys.append(key)

    return [
        {
            "key": key,
            "title": key,
            "width": _COLUMN_WIDTHS.get(key, _DEFAULT_WIDTH),
        }
        for key in ordered_keys
    ]


def flatten_articles(
    client,
    articles: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (snapshot_data_rows, indexed_field_dicts, columns)."""
    lookups = build_lookups(client, articles)
    snapshot_rows: list[dict[str, str]] = []
    indexed: list[dict[str, Any]] = []
    for article in articles:
        master = article_to_master_row(article, lookups)
        data = master_row_to_snapshot_data(master)
        snapshot_rows.append(data)
        version = article.get("version")
        indexed.append(
            extract_indexed_fields(
                data,
                weclapp_id=str(article.get("id") or ""),
                weclapp_version=str(version) if version is not None else None,
            )
        )
    columns = build_snapshot_columns(snapshot_rows)
    return snapshot_rows, indexed, columns


__all__ = [
    "build_lookups",
    "article_to_master_row",
    "build_snapshot_columns",
    "extract_indexed_fields",
    "flatten_articles",
    "master_row_to_snapshot_data",
]
