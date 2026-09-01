"""Build weclapp article create payloads from import-template rows.

One definition used by the CLI importer and the web batch submit path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

NUMBER_PLACEHOLDER = "wird autogeneriert"

ARTICLE_NUMBER_FIELD = "Prosema-Artikelnummer"
ARTICLE_NAME_FIELD = "Prosema-Artikelname"
LONG_TEXT_FIELD = "Prosema-Langtext"

# Historic registration-template labels still present in v1 rows / files.
LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    ARTICLE_NUMBER_FIELD: ("Prosema Artikelnummer",),
    ARTICLE_NAME_FIELD: ("PROSEMA Kurztext", "Prosema Kurztext"),
    LONG_TEXT_FIELD: ("PROSEMA Langtext", "Prosema Langtext"),
}

_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical
    for canonical, aliases in LABEL_ALIASES.items()
    for alias in aliases
}

STRING_CUSTOM_ATTRS: dict[str, str] = {
    "Grundmaterial": "Grundmaterial",
    "Oberfläche": "Oberfläche",
    "Farbe": "Farbe",
    "Produktfamilie": "Produktfamilie",
    "Rabattcode": "Rabattcode",
    "Verkaufseinheit": "Verkaufseinheit",
    "Verpackung": "Verpackung",
    "VPE 1": "VPE 1",
    "VPE 2": "VPE 2",
    "VPE 3": "VPE 3",
    "Breite in mm": "Breite in mm",
    "Länge in cm": "Länge in cm",
    "Höhe in mm": "Höhe in mm",
    "Gewichtseinheit": "Gewichtseinheit",
    "Produkt-ID (Prosema)": "Produkt-ID (Prosema)",
    "Varianten-ID (Prosema)": "Varianten-ID (Prosema)",
}

BOOLEAN_CUSTOM_ATTRS: dict[str, str] = {
    "Im Shop verfügbar": "Im Shop verfügbar (Prosema)",
    "Im Shop aktiv": "Im Shop aktiv (Prosema)",
    "Bestand übertragen": "Bestand übertragen (Prosema)",
    "Bodenleger": "Bodenleger",
    "Dachdecker": "Dachdecker",
    "Landschaftsgärtner": "Landschaftsgärtner",
    "Plattenleger": "Plattenleger",
}

# Best-effort writes onto weclapp Shopify lists. Valid groups come from
# Gruppenverwaltung, not from these selectable-value catalogues.
LIST_CUSTOM_ATTRS: dict[str, str] = {
    "Hauptgruppe": "Hauptwarengruppe (Auswahl)",
    "Untergruppe": "Warengruppe (Auswahl)",
}

DEFAULTS: dict[str, str] = {
    ARTICLE_NUMBER_FIELD: NUMBER_PLACEHOLDER,
    "Artikeltyp": "STORABLE",
    "Einheit": "Stk.",
    "Aktiv": "Ja",
    "Im Verkauf": "Ja",
    "Steuersatz": "STANDARD",
    "Im Shop verfügbar": "Ja",
    "Im Shop aktiv": "Ja",
    "Bestand übertragen": "Ja",
    "Gewichtseinheit": "kg",
}

TRUE_VALUES = {"ja", "true", "1", "yes", "x"}
FALSE_VALUES = {"nein", "false", "0", "no", ""}


class LookupTablesProtocol(Protocol):
    def unit_id(self, value: str) -> str: ...

    def category_id(self, value: str) -> str | None: ...

    def list_value_id(self, attr_label: str, value: str) -> str: ...

    def attr_id(self, label: str) -> str: ...


def canonical_label(label: str) -> str:
    return _ALIAS_TO_CANONICAL.get(str(label or "").strip(), str(label or "").strip())


def label_variants(label: str) -> tuple[str, ...]:
    """Canonical catalogue name plus historic aliases."""
    canonical = canonical_label(label)
    seen: dict[str, None] = {canonical: None}
    for alias in LABEL_ALIASES.get(canonical, ()):
        seen.setdefault(alias, None)
    if label and label not in seen:
        seen[label] = None
    return tuple(seen)


def get_row_value(row: Mapping[str, Any], column: str) -> str:
    """Read a cell, accepting historic aliases of renamed catalogue labels."""
    for key in label_variants(column):
        raw = _norm(row.get(key, ""))
        if raw:
            return raw
    return ""


def _norm(value: object) -> str:
    return str(value or "").strip()


def _parse_bool(value: object, *, default: bool | None = None) -> bool | None:
    text = _norm(value).lower()
    if not text:
        return default
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError(f"Ungültiger Ja/Nein-Wert: {value!r}")


def _row_value(row: dict[str, str], column: str) -> str:
    raw = get_row_value(row, column)
    if raw:
        return raw
    return DEFAULTS.get(canonical_label(column), DEFAULTS.get(column, ""))


def _optional_list_value_id(
    lookups: LookupTablesProtocol, attr_label: str, value: str
) -> str | None:
    """weclapp option id, or None when the Shopify list has not caught up.

    Missing attribute *definitions* still raise: that is a schema problem.
    Missing *options* are skipped so Gruppenverwaltung can add groups without
    also extending weclapp's Hauptwarengruppe / Warengruppe lists first.
    """
    finder = getattr(lookups, "find_list_value_id", None)
    if callable(finder):
        return finder(attr_label, value)
    try:
        return lookups.list_value_id(attr_label, value)
    except ValueError as exc:
        if str(exc).startswith("Ungültiger Wert für"):
            return None
        raise


def row_to_payload(row: dict[str, str], lookups: LookupTablesProtocol) -> dict[str, Any]:
    article_number = _row_value(row, ARTICLE_NUMBER_FIELD)
    name = _row_value(row, ARTICLE_NAME_FIELD)
    if not article_number or article_number == NUMBER_PLACEHOLDER:
        raise ValueError(
            "Prosema-Artikelnummer fehlt. Bitte Hauptgruppe und Untergruppe setzen "
            "und Artikelnummern erzeugen."
        )
    if not name:
        raise ValueError("Prosema-Artikelname fehlt")

    unit_value = _row_value(row, "Einheit")
    payload: dict[str, Any] = {
        "articleNumber": article_number,
        "name": name,
        "articleType": _row_value(row, "Artikeltyp").upper() or "STORABLE",
        "unitId": lookups.unit_id(unit_value),
        "taxRateType": _row_value(row, "Steuersatz").upper() or "STANDARD",
        "active": _parse_bool(_row_value(row, "Aktiv"), default=True),
        "availableInSale": _parse_bool(_row_value(row, "Im Verkauf"), default=True),
    }

    match_code = _row_value(row, "Referenz (Matchcode)")
    if match_code:
        payload["matchCode"] = match_code
    ean = _row_value(row, "GTIN (EAN-Nummer)")
    if ean:
        payload["ean"] = ean
    short_description = _row_value(row, "Kurzbeschreibung") or name
    payload["shortDescription1"] = short_description
    long_text = _row_value(row, LONG_TEXT_FIELD)
    if long_text:
        payload["longText"] = long_text
    category = _row_value(row, "Kategorie")
    if category:
        payload["articleCategoryId"] = lookups.category_id(category)
    weight = _row_value(row, "Nettogewicht kg")
    if weight:
        payload["articleNetWeight"] = weight.replace(",", ".")

    custom_attributes: list[dict[str, Any]] = []
    html = _row_value(row, "Artikelbeschreibung HTML")
    if html:
        custom_attributes.append(
            {
                "attributeDefinitionId": lookups.attr_id("Artikelbeschreibung (Prosema)"),
                "stringValue": html,
            }
        )

    for column, label in STRING_CUSTOM_ATTRS.items():
        value = _row_value(row, column)
        if not value:
            continue
        custom_attributes.append(
            {
                "attributeDefinitionId": lookups.attr_id(label),
                "stringValue": value,
            }
        )

    for column, label in BOOLEAN_CUSTOM_ATTRS.items():
        value = _row_value(row, column)
        parsed = _parse_bool(value, default=None)
        if parsed is None:
            continue
        custom_attributes.append(
            {
                "attributeDefinitionId": lookups.attr_id(label),
                "booleanValue": parsed,
            }
        )

    for column, label in LIST_CUSTOM_ATTRS.items():
        value = _row_value(row, column)
        if not value:
            continue
        option_id = _optional_list_value_id(lookups, label, value)
        if option_id is None:
            continue
        custom_attributes.append(
            {
                "attributeDefinitionId": lookups.attr_id(label),
                "selectedValueId": option_id,
            }
        )

    if custom_attributes:
        payload["customAttributes"] = custom_attributes
    return payload
