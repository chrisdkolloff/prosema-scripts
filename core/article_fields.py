"""Article import field catalogue.

Code-owned: labels, types, upload/payload/edit rules, and which columns may
never leave the template. The database template only chooses which catalogue
fields appear and in what order.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.article_payload import (
    ARTICLE_NAME_FIELD,
    ARTICLE_NUMBER_FIELD,
    BOOLEAN_CUSTOM_ATTRS,
    DEFAULTS,
    LABEL_ALIASES,
    LIST_CUSTOM_ATTRS,
    LONG_TEXT_FIELD,
    NUMBER_PLACEHOLDER,
    STRING_CUSTOM_ATTRS,
)


@dataclass(frozen=True)
class ArticleField:
    """One import-template column.

    ``required_for_upload``, ``in_payload`` and ``never_editable`` are distinct.
    ``protected_reason`` is separate again: a field can be non-removable from
    the template without being an upload requirement (and vice versa is
    unusual — upload-required fields are always protected).
    """

    label: str
    key: str
    field_type: str
    required_for_upload: bool
    in_payload: bool
    never_editable: bool
    protected_reason: str | None
    example: str
    description: str

    @property
    def protected(self) -> bool:
        return self.protected_reason is not None


_CORE_PAYLOAD_LABELS = frozenset(
    {
        ARTICLE_NUMBER_FIELD,
        ARTICLE_NAME_FIELD,
        LONG_TEXT_FIELD,
        "Kurzbeschreibung",
        "Referenz (Matchcode)",
        "GTIN (EAN-Nummer)",
        "Artikeltyp",
        "Einheit",
        "Kategorie",
        "Aktiv",
        "Im Verkauf",
        "Steuersatz",
        "Nettogewicht kg",
        "Artikelbeschreibung HTML",
    }
)

_UPLOAD_REQUIRED = frozenset({ARTICLE_NAME_FIELD, "Hauptgruppe", "Untergruppe"})

_NEVER_EDITABLE = frozenset(
    {
        ARTICLE_NUMBER_FIELD,
        "Produkt-ID (Prosema)",
        "Varianten-ID (Prosema)",
    }
)

_SELECT_LABELS = frozenset(
    {
        "Artikeltyp",
        "Einheit",
        "Kategorie",
        "Aktiv",
        "Im Verkauf",
        "Steuersatz",
        "Im Shop verfügbar",
        "Im Shop aktiv",
        "Bestand übertragen",
        "Gewichtseinheit",
        "Bodenleger",
        "Dachdecker",
        "Landschaftsgärtner",
        "Plattenleger",
        "Hauptgruppe",
        "Untergruppe",
    }
)

_BOOL_LABELS = frozenset(BOOLEAN_CUSTOM_ATTRS) | {"Aktiv", "Im Verkauf"}

_DESCRIPTIONS: dict[str, str] = {
    ARTICLE_NUMBER_FIELD: "Wird aus Haupt- und Untergruppe abgeleitet, nie aus der Datei übernommen.",
    "Lieferantenartikelnummer": "Lieferanten-eigene Artikelnummer; Teil des Bezugsquellen-Matchschlüssels.",
    "Hauptgruppe": "Registry-Hauptgruppe (Name - Code). Voraussetzung für die Artikelnummer.",
    "Untergruppe": "Registry-Untergruppe (Name - Code). Voraussetzung für die Artikelnummer.",
    ARTICLE_NAME_FIELD: "Artikelname in weclapp (name). Pflicht für die Anlage.",
    LONG_TEXT_FIELD: "Langer Beschreibungstext (longText).",
    "Kurzbeschreibung": "Kurze Beschreibung (shortDescription1); fällt auf den Artikelnamen zurück.",
    "Referenz (Matchcode)": "Matchcode / Referenz in weclapp.",
    "GTIN (EAN-Nummer)": "EAN/GTIN.",
    "Artikeltyp": "weclapp-Artikeltyp, typischerweise BASIC.",
    "Einheit": "Mengeneinheit (unitId).",
    "Kategorie": "weclapp-Artikelkategorie.",
    "Aktiv": "Artikel aktiv in weclapp.",
    "Im Verkauf": "Im Verkauf verfügbar.",
    "Steuersatz": "Steuersatztyp, typischerweise STANDARD.",
    "Im Shop verfügbar": "Custom-Attribut Shop-Verfügbarkeit.",
    "Im Shop aktiv": "Custom-Attribut Shop-Aktiv.",
    "Bestand übertragen": "Custom-Attribut Bestand übertragen.",
    "Gewichtseinheit": "Custom-Attribut Gewichtseinheit.",
    "Grundmaterial": "Custom-Attribut Grundmaterial.",
    "Oberfläche": "Custom-Attribut Oberfläche.",
    "Farbe": "Custom-Attribut Farbe.",
    "Produktfamilie": "Custom-Attribut Produktfamilie.",
    "Rabattcode": "Custom-Attribut Rabattcode.",
    "Verkaufseinheit": "Custom-Attribut Verkaufseinheit.",
    "Verpackung": "Custom-Attribut Verpackung.",
    "VPE 1": "Custom-Attribut Verpackungseinheit 1.",
    "VPE 2": "Custom-Attribut Verpackungseinheit 2.",
    "VPE 3": "Custom-Attribut Verpackungseinheit 3.",
    "Breite in mm": "Custom-Attribut Breite.",
    "Länge in cm": "Custom-Attribut Länge.",
    "Höhe in mm": "Custom-Attribut Höhe.",
    "Bodenleger": "Custom-Attribut Zielgruppe Bodenleger.",
    "Dachdecker": "Custom-Attribut Zielgruppe Dachdecker.",
    "Landschaftsgärtner": "Custom-Attribut Zielgruppe Landschaftsgärtner.",
    "Plattenleger": "Custom-Attribut Zielgruppe Plattenleger.",
    "Artikelbeschreibung HTML": "HTML-Beschreibung (Custom-Attribut).",
    "Nettogewicht kg": "Nettogewicht in kg (articleNetWeight).",
    "Produkt-ID (Prosema)": "Interne Produkt-ID; nicht bearbeitbar.",
    "Varianten-ID (Prosema)": "Interne Varianten-ID; nicht bearbeitbar.",
}

_EXAMPLES: dict[str, str] = {
    ARTICLE_NUMBER_FIELD: NUMBER_PLACEHOLDER,
    "Lieferantenartikelnummer": "TEST-SUP-001",
    "Hauptgruppe": "Zubehör - 020",
    "Untergruppe": "Nivelliersystem - 010",
    ARTICLE_NAME_FIELD: "TEST Dummy Artikel",
    LONG_TEXT_FIELD: "Testdatensatz für den Artikelimport.",
    "Kurzbeschreibung": "TEST Dummy Artikel",
    "Referenz (Matchcode)": "TEST-DUMMY",
    "GTIN (EAN-Nummer)": "",
    "Artikeltyp": "BASIC",
    "Einheit": "Stk.",
    "Kategorie": "Zubehör allgemein",
    "Aktiv": "Ja",
    "Im Verkauf": "Ja",
    "Steuersatz": "STANDARD",
    "Im Shop verfügbar": "Ja",
    "Im Shop aktiv": "Ja",
    "Bestand übertragen": "Ja",
    "Gewichtseinheit": "kg",
    "Grundmaterial": "Testdaten",
    "Oberfläche": "",
    "Farbe": "Testfarbe",
    "Produktfamilie": "",
    "Rabattcode": "",
    "Verkaufseinheit": "Stk.",
    "Verpackung": "1",
    "VPE 1": "",
    "VPE 2": "",
    "VPE 3": "",
    "Breite in mm": "",
    "Länge in cm": "",
    "Höhe in mm": "",
    "Bodenleger": "Nein",
    "Dachdecker": "Nein",
    "Landschaftsgärtner": "Nein",
    "Plattenleger": "Nein",
    "Artikelbeschreibung HTML": "<p>Testdatensatz.</p>",
    "Nettogewicht kg": "0.1",
    "Produkt-ID (Prosema)": "",
    "Varianten-ID (Prosema)": "",
}

# Order matches the historic import template / IMPORT_COLUMNS.
_LABEL_ORDER: tuple[str, ...] = (
    ARTICLE_NUMBER_FIELD,
    "Lieferantenartikelnummer",
    "Hauptgruppe",
    "Untergruppe",
    ARTICLE_NAME_FIELD,
    LONG_TEXT_FIELD,
    "Kurzbeschreibung",
    "Referenz (Matchcode)",
    "GTIN (EAN-Nummer)",
    "Artikeltyp",
    "Einheit",
    "Kategorie",
    "Aktiv",
    "Im Verkauf",
    "Steuersatz",
    "Im Shop verfügbar",
    "Im Shop aktiv",
    "Bestand übertragen",
    "Gewichtseinheit",
    "Grundmaterial",
    "Oberfläche",
    "Farbe",
    "Produktfamilie",
    "Rabattcode",
    "Verkaufseinheit",
    "Verpackung",
    "VPE 1",
    "VPE 2",
    "VPE 3",
    "Breite in mm",
    "Länge in cm",
    "Höhe in mm",
    "Bodenleger",
    "Dachdecker",
    "Landschaftsgärtner",
    "Plattenleger",
    "Artikelbeschreibung HTML",
    "Nettogewicht kg",
    "Produkt-ID (Prosema)",
    "Varianten-ID (Prosema)",
)

_PFICHT_REASON = "Pflichtfeld — kann nicht entfernt werden."
_SUPPLIER_REASON = "Wird für die Zuordnung von Bezugsquellen benötigt."


def _field_type(label: str) -> str:
    if label == "Artikelbeschreibung HTML":
        return "html"
    if label == "Nettogewicht kg":
        return "number"
    if label in _BOOL_LABELS:
        return "bool"
    if label in _SELECT_LABELS or label in LIST_CUSTOM_ATTRS:
        return "select"
    return "text"


def _in_payload(label: str) -> bool:
    if label in _CORE_PAYLOAD_LABELS:
        return True
    if label in STRING_CUSTOM_ATTRS:
        return True
    if label in BOOLEAN_CUSTOM_ATTRS:
        return True
    return label in LIST_CUSTOM_ATTRS


def _protected_reason(label: str) -> str | None:
    if label in _UPLOAD_REQUIRED:
        return _PFICHT_REASON
    if label == "Lieferantenartikelnummer":
        return _SUPPLIER_REASON
    return None


def _build_fields() -> tuple[ArticleField, ...]:
    fields: list[ArticleField] = []
    for label in _LABEL_ORDER:
        example = _EXAMPLES.get(label)
        if example is None:
            example = DEFAULTS.get(label, "")
        fields.append(
            ArticleField(
                label=label,
                key=label,
                field_type=_field_type(label),
                required_for_upload=label in _UPLOAD_REQUIRED,
                in_payload=_in_payload(label),
                never_editable=label in _NEVER_EDITABLE,
                protected_reason=_protected_reason(label),
                example=example,
                description=_DESCRIPTIONS.get(label, ""),
            )
        )
    return tuple(fields)


FIELDS: tuple[ArticleField, ...] = _build_fields()

IMPORT_COLUMNS: tuple[str, ...] = tuple(field.label for field in FIELDS)

REQUIRED_UPLOAD_HEADERS: frozenset[str] = frozenset(
    field.label for field in FIELDS if field.required_for_upload
)

PROTECTED_FIELDS: tuple[ArticleField, ...] = tuple(f for f in FIELDS if f.protected)

BY_LABEL: dict[str, ArticleField] = {field.label: field for field in FIELDS}

_BY_LABEL_FOLD: dict[str, ArticleField] = {
    field.label.casefold(): field for field in FIELDS
}

for _canonical, _aliases in LABEL_ALIASES.items():
    _field = BY_LABEL[_canonical]
    for _alias in _aliases:
        BY_LABEL.setdefault(_alias, _field)
        _BY_LABEL_FOLD.setdefault(_alias.casefold(), _field)


def normalize_label(value: object) -> str:
    return str(value or "").strip()


def find_field(label: object) -> ArticleField | None:
    """Match a header to the catalogue; case, whitespace, and historic aliases."""
    cleaned = normalize_label(label)
    if not cleaned:
        return None
    direct = BY_LABEL.get(cleaned)
    if direct is not None:
        return direct
    return _BY_LABEL_FOLD.get(cleaned.casefold())


def seed_template_columns() -> list[dict[str, object]]:
    """Ordered columns JSON for the seeded v1 template (full catalogue)."""
    return [
        {
            "key": field.key,
            "label": field.label,
            "required": field.required_for_upload,
        }
        for field in FIELDS
    ]
