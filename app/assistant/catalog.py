"""Queryable article-snapshot catalogue.

Group codes are NOT read from ``ArticleSnapshotRow.hauptgruppe_code`` /
``untergruppe_code``. In the measured snapshot those columns hold weclapp
category *names* (4175/4175 fail ``^[0-9]{3}$``), so they are deliberately
unused. Codes are taken from a conforming article number instead:

    hauptgruppe = substring(article_number from 1 for 3)
    untergruppe = substring(article_number from 5 for 3)

guarded by ``article_number ~ '^[0-9]{3}\\.[0-9]{3}\\.[0-9]{4}$'``. Rows that
fail the pattern (``ArticleSnapshot.non_conforming_number_count``) yield NULL.

Empty vs missing is not interchangeable. Keys that appear in
``core.article_fields.IMPORT_COLUMNS`` are always present in JSONB, with ``''``
for no value (``empty_encoding="empty_string"``). Master-export extras are
omitted from the JSON object when empty (``empty_encoding="absent"``). Treating
both as SQL NULL mis-counts.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import ColumnElement, bindparam, case, cast, false, func, not_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Numeric

from app.assistant.schemas import Operator
from app.config import settings
from app.models import ArticleSnapshot, ArticleSnapshotRow
from core.article_fields import IMPORT_COLUMNS
from core.article_payload import ARTICLE_NAME_FIELD, ARTICLE_NUMBER_FIELD, LONG_TEXT_FIELD

Storage = Literal["column", "jsonb", "virtual"]
ColumnType = Literal["text", "number", "bool", "select"]
NumericFormat = Literal["comma", "dot"]
EmptyEncoding = Literal["empty_string", "absent"]

GEWICHT_UNIT_EQUIV: frozenset[str] = frozenset({"kg", "KILOGRAM"})
SELECT_CACHE_TTL_SECONDS = 300
CONFORMING_NUMBER_PATTERN = r"^[0-9]{3}\.[0-9]{3}\.[0-9]{4}$"
COMMA_NUMBER_PATTERN = r"^-?[0-9]+(,[0-9]+)?$"
DOT_NUMBER_PATTERN = r"^-?[0-9]+(\.[0-9]+)?$"

_TEXT_OPS: tuple[Operator, ...] = (
    Operator.eq,
    Operator.ne,
    Operator.contains,
    Operator.starts_with,
    Operator.is_null,
    Operator.is_not_null,
    Operator.in_list,
)
_NUMBER_OPS: tuple[Operator, ...] = (
    Operator.eq,
    Operator.ne,
    Operator.gt,
    Operator.gte,
    Operator.lt,
    Operator.lte,
    Operator.is_null,
    Operator.is_not_null,
)
_BOOL_OPS: tuple[Operator, ...] = (
    Operator.eq,
    Operator.ne,
    Operator.is_null,
    Operator.is_not_null,
)
_SELECT_OPS: tuple[Operator, ...] = (
    Operator.eq,
    Operator.ne,
    Operator.in_list,
    Operator.is_null,
    Operator.is_not_null,
)
_OPS: dict[ColumnType, tuple[Operator, ...]] = {
    "text": _TEXT_OPS,
    "number": _NUMBER_OPS,
    "bool": _BOOL_OPS,
    "select": _SELECT_OPS,
}


@dataclass(frozen=True)
class QueryableColumn:
    name: str
    aliases: tuple[str, ...]
    storage: Storage
    column_attr: str | None
    type: ColumnType
    numeric_format: NumericFormat | None
    empty_encoding: EmptyEncoding
    label_de: str
    description_de: str
    allowed_operators: tuple[Operator, ...]
    filterable: bool
    sortable: bool

    @property
    def json_keys(self) -> tuple[str, ...]:
        if self.storage in ("column", "virtual"):
            return self.aliases
        return (self.name, *self.aliases)


_SELECT_CACHE: dict[tuple[uuid.UUID, str], tuple[float, tuple[str, ...]]] = {}
_HEADER_CACHE: dict[uuid.UUID, tuple[float, tuple[str, ...]]] = {}


def _empty_encoding(storage: Storage, *keys: str) -> EmptyEncoding:
    if storage in ("column", "virtual"):
        return "empty_string"
    if any(key in IMPORT_COLUMNS for key in keys if key):
        return "empty_string"
    return "absent"


def _q(
    name: str,
    *,
    type: ColumnType,
    description_de: str,
    aliases: tuple[str, ...] = (),
    storage: Storage = "jsonb",
    column_attr: str | None = None,
    numeric_format: NumericFormat | None = None,
    label_de: str | None = None,
    filterable: bool = True,
    sortable: bool = True,
    allowed_operators: tuple[Operator, ...] | None = None,
) -> QueryableColumn:
    if storage == "column" and not column_attr:
        raise ValueError(f"{name} is column storage without column_attr")
    if type == "number" and numeric_format is None:
        raise ValueError(f"{name} is number without numeric_format")
    keys = (name, *aliases) if storage == "jsonb" else aliases
    return QueryableColumn(
        name=name,
        aliases=aliases,
        storage=storage,
        column_attr=column_attr,
        type=type,
        numeric_format=numeric_format,
        empty_encoding=_empty_encoding(storage, *keys),
        label_de=label_de or name,
        description_de=description_de,
        allowed_operators=allowed_operators if allowed_operators is not None else _OPS[type],
        filterable=filterable,
        sortable=sortable,
    )


COLUMNS: tuple[QueryableColumn, ...] = (
    _q(
        "article_number",
        type="text",
        storage="column",
        column_attr="article_number",
        aliases=(ARTICLE_NUMBER_FIELD, "Prosema Artikelnummer", "Prosema-Art.-Nr."),
        label_de="Prosema-Art.-Nr.",
        description_de=(
            "Artikelnummer. Konforme Nummern haben die Form MMM.SSS.NNNN; "
            "daraus werden Haupt- und Untergruppe gelesen."
        ),
    ),
    _q(
        "article_name",
        type="text",
        storage="column",
        column_attr="article_name",
        aliases=(ARTICLE_NAME_FIELD, "PROSEMA Kurztext"),
        label_de="Prosema-Artikelname",
        description_de="Artikelname (Kurztext).",
    ),
    _q(
        "volltext",
        type="text",
        storage="virtual",
        label_de="Volltext",
        filterable=True,
        sortable=False,
        allowed_operators=(Operator.contains,),
        description_de=(
            "Durchsucht gleichzeitig Artikelname, Kurzbeschreibung, Prosema-Langtext, "
            "Grundmaterial, Farbe, Oberfläche und Produktfamilie. "
            "Richtige Wahl für Materialien, Farben und Begriffe, die in "
            "unterschiedlichen Feldern stehen können."
        ),
    ),
    _q(
        "active",
        type="bool",
        storage="column",
        column_attr="active",
        aliases=("Aktiv",),
        label_de="Aktiv",
        description_de="Ob der Artikel in weclapp aktiv ist. Werte: Ja, Nein.",
    ),
    _q(
        "weclapp_id",
        type="text",
        storage="column",
        column_attr="weclapp_id",
        aliases=("weclapp Artikel-ID",),
        label_de="weclapp-ID",
        description_de="Interne weclapp-ID. Identifikator, keine Menge.",
    ),
    _q(
        "Lieferantenartikelnummer",
        type="text",
        aliases=("Lieferanten-Art.-Nr.",),
        label_de="Lieferanten-Art.-Nr.",
        description_de=(
            "Artikelnummer beim Lieferanten. Identifikator, keine Menge — "
            "nicht numerisch vergleichen."
        ),
    ),
    _q(
        "Hauptgruppe",
        type="select",
        description_de=(
            "Hauptgruppe als deutscher Name, nicht als dreistelliger Code. "
            "Die Codes stehen in der Artikelnummer (erste drei Stellen)."
        ),
    ),
    _q(
        "Untergruppe",
        type="text",
        description_de=(
            "Untergruppe als deutscher Name. Für den Code die Stellen 5–7 der "
            "Artikelnummer verwenden; gruppen_auflisten listet Code und Name."
        ),
    ),
    _q(
        LONG_TEXT_FIELD,
        type="text",
        aliases=("PROSEMA Langtext",),
        label_de="Prosema-Langtext",
        sortable=False,
        description_de="Langer Beschreibungstext.",
    ),
    _q(
        "Kurzbeschreibung",
        type="text",
        description_de="Kurze Beschreibung.",
    ),
    _q(
        "Referenz (Matchcode)",
        type="text",
        description_de="Matchcode / Referenz. Identifikator, keine Menge.",
    ),
    _q(
        "GTIN (EAN-Nummer)",
        type="text",
        # Identifier: 4137/4137 values are digit strings, not quantities.
        description_de="EAN/GTIN. Identifikator, keine Menge — nicht numerisch vergleichen.",
    ),
    _q(
        "Artikeltyp",
        type="select",
        description_de="weclapp-Artikeltyp (z. B. STORABLE, BASIC).",
    ),
    _q(
        "Einheit",
        type="select",
        description_de=(
            "Mengeneinheit. Nicht mit Verkaufseinheit verwechseln: dieselbe Idee "
            "heisst hier «Stk.», dort «Stück». Werte der einen Liste sind in der "
            "anderen nicht gültig."
        ),
    ),
    _q(
        "Kategorie",
        type="text",
        description_de="weclapp-Artikelkategorie (freier Name).",
    ),
    _q(
        "Im Shop verfügbar",
        type="select",
        description_de="Custom-Attribut Shop-Verfügbarkeit. Werte: Ja, Nein.",
    ),
    _q(
        "Im Shop aktiv",
        type="select",
        description_de="Custom-Attribut Shop-Aktiv. Werte: Ja, Nein.",
    ),
    _q(
        "Gewichtseinheit",
        type="select",
        description_de=(
            "Gewichtseinheit. KILOGRAM und kg werden als dasselbe behandelt."
        ),
    ),
    _q(
        "Grundmaterial",
        type="text",
        description_de="Custom-Attribut Grundmaterial.",
    ),
    _q(
        "Oberfläche",
        type="text",
        description_de=(
            "Oberfläche als Text. Werte können mehrere Angaben mit Komma enthalten "
            "(z. B. «eloxiert,gebürstet»); deshalb contains, nicht Gleichheit."
        ),
    ),
    _q(
        "Farbe",
        type="text",
        description_de="Custom-Attribut Farbe.",
    ),
    _q(
        "Produktfamilie",
        type="text",
        description_de="Custom-Attribut Produktfamilie.",
    ),
    _q(
        "Rabattcode",
        type="select",
        description_de="Custom-Attribut Rabattcode (z. B. A, NET, T).",
    ),
    _q(
        "Verkaufseinheit",
        type="select",
        description_de=(
            "Verkaufseinheit. Nicht mit Einheit verwechseln: hier «Stück», dort "
            "«Stk.». Werte nicht über die beiden Felder hinweg annehmen."
        ),
    ),
    _q(
        "Verpackung",
        type="text",
        description_de="Custom-Attribut Verpackung.",
    ),
    _q(
        "VPE 1",
        type="text",
        # Measured: both 1,00 and 1.000 occur; thousands vs decimal is undecidable.
        description_de=(
            "Verpackungseinheit 1. Enthält gemischte Schreibweisen (1,00 und 1.000); "
            "nicht numerisch vergleichen."
        ),
    ),
    _q(
        "VPE 2",
        type="text",
        # Measured: both 1,00 and 1.000 occur; thousands vs decimal is undecidable.
        description_de=(
            "Verpackungseinheit 2. Enthält gemischte Schreibweisen (1,00 und 1.000); "
            "nicht numerisch vergleichen."
        ),
    ),
    _q(
        "VPE 3",
        type="text",
        # Measured: both 1,00 and 1.000 occur; thousands vs decimal is undecidable.
        description_de=(
            "Verpackungseinheit 3. Enthält gemischte Schreibweisen (1,00 und 1.000); "
            "nicht numerisch vergleichen."
        ),
    ),
    _q(
        "Breite in mm",
        type="number",
        numeric_format="comma",
        description_de="Breite in Millimeter. Dezimaltrennzeichen ist das Komma.",
    ),
    _q(
        "Länge in cm",
        type="number",
        numeric_format="comma",
        description_de="Länge in Zentimeter. Dezimaltrennzeichen ist das Komma.",
    ),
    _q(
        "Höhe in mm",
        type="number",
        numeric_format="comma",
        description_de="Höhe in Millimeter. Dezimaltrennzeichen ist das Komma.",
    ),
    _q(
        "Nettogewicht kg",
        type="number",
        numeric_format="comma",
        description_de="Nettogewicht in Kilogramm. Dezimaltrennzeichen ist das Komma.",
    ),
    _q(
        "Nettoverkaufspreis CHF",
        type="number",
        numeric_format="dot",
        aliases=("Verkaufspreis €, BE",),
        description_de="Nettoverkaufspreis in CHF. Dezimaltrennzeichen ist der Punkt.",
    ),
    _q(
        "Einkaufspreis EUR netto",
        type="number",
        numeric_format="dot",
        description_de="Einkaufspreis netto in Euro. Dezimaltrennzeichen ist der Punkt.",
    ),
    _q(
        "Lieferanten Firmenname",
        type="select",
        aliases=("Name Lieferant",),
        label_de="Name Lieferant",
        description_de="Name des Lieferanten.",
    ),
    _q(
        "Lieferantennummer",
        type="text",
        # Identifier: 4122/4122 values are digit strings, not quantities.
        description_de="Lieferantennummer. Identifikator, keine Menge — nicht numerisch vergleichen.",
    ),
    _q(
        "Zolltarifnummer",
        type="text",
        # 42 HS codes; starts_with is more useful than an enumeration.
        description_de=(
            "Zolltarifnummer (HS-Code). Identifikator; mit starts_with nach Präfix filtern, "
            "nicht als Menge vergleichen."
        ),
    ),
)

COLUMNS_BY_NAME: dict[str, QueryableColumn] = {col.name: col for col in COLUMNS}
VOLLTEXT_COLUMNS: tuple[str, ...] = (
    "article_name",
    "Kurzbeschreibung",
    LONG_TEXT_FIELD,
    "Grundmaterial",
    "Farbe",
    "Oberfläche",
    "Produktfamilie",
)
_LOOKUP: dict[str, QueryableColumn] = {}
for _col in COLUMNS:
    _LOOKUP[_col.name.casefold()] = _col
    _LOOKUP[_col.label_de.casefold()] = _col
    for _alias in _col.aliases:
        _LOOKUP[_alias.casefold()] = _col


def column_names() -> list[str]:
    return [col.name for col in COLUMNS]


def get_column(name: str) -> QueryableColumn | None:
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    return _LOOKUP.get(cleaned.casefold())


def numeric_rejected_message(col: QueryableColumn) -> str:
    if col.name.startswith("VPE "):
        return (
            f"«{col.label_de}» kann nicht numerisch verglichen werden, "
            "weil Komma- und Punkt-Schreibweisen gemischt vorkommen."
        )
    return (
        f"«{col.label_de}» kann nicht numerisch verglichen werden "
        f"(Typ {col.type}, kein Zahlenfeld)."
    )


def _snapshot_for_catalog(session: Session) -> ArticleSnapshot | None:
    tenant = settings.weclapp_tenant.strip()
    return session.scalars(
        select(ArticleSnapshot)
        .where(
            ArticleSnapshot.status == "complete",
            ArticleSnapshot.weclapp_tenant == tenant,
        )
        .order_by(ArticleSnapshot.created_at.desc())
        .limit(1)
    ).first()


def _header_keys(session: Session, snapshot: ArticleSnapshot) -> tuple[str, ...]:
    now = time.monotonic()
    cached = _HEADER_CACHE.get(snapshot.id)
    if cached is not None and cached[0] > now:
        return cached[1]
    columns = snapshot.columns or []
    keys = tuple(
        str(col.get("key", ""))
        for col in columns
        if isinstance(col, dict) and col.get("key")
    )
    _HEADER_CACHE[snapshot.id] = (now + SELECT_CACHE_TTL_SECONDS, keys)
    return keys


def resolve_key(session: Session, col: QueryableColumn) -> str | None:
    """First alias present in the current snapshot header, else None."""
    snapshot = _snapshot_for_catalog(session)
    if snapshot is None:
        return None
    header = set(_header_keys(session, snapshot))
    for key in col.json_keys:
        if key in header:
            return key
    return None


def _json_key_bind(key: str) -> bindparam:
    return bindparam(None, key, unique=True)


def _contains_pattern(value: str) -> str:
    escaped = (
        str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def column_expression(session: Session, col: QueryableColumn) -> ColumnElement:
    if col.storage == "virtual":
        raise ValueError(
            f"Die virtuelle Spalte «{col.label_de}» hat keinen einzelnen Spaltenausdruck."
        )
    if col.storage == "column":
        return getattr(ArticleSnapshotRow, col.column_attr)
    key = resolve_key(session, col)
    if key is None:
        raise ValueError(
            f"Die Spalte «{col.label_de}» ist in diesem Snapshot nicht vorhanden."
        )
    return ArticleSnapshotRow.data[_json_key_bind(key)].astext


def volltext_expression(session: Session, value: str) -> ColumnElement:
    """OR of ILIKE '%value%' over VOLLTEXT_COLUMNS present in this snapshot."""
    pattern = _contains_pattern(value)
    clauses: list[ColumnElement] = []
    for name in VOLLTEXT_COLUMNS:
        col = COLUMNS_BY_NAME[name]
        if col.storage == "column":
            expr = getattr(ArticleSnapshotRow, col.column_attr)
        else:
            key = resolve_key(session, col)
            if key is None:
                continue
            expr = ArticleSnapshotRow.data[_json_key_bind(key)].astext
        clauses.append(expr.ilike(pattern, escape="\\"))
    if not clauses:
        return false()
    return or_(*clauses)


def numeric_expression(session: Session, col: QueryableColumn) -> ColumnElement:
    if col.type != "number" or col.numeric_format is None:
        raise ValueError(numeric_rejected_message(col))
    raw = column_expression(session, col)
    if col.numeric_format == "comma":
        pattern = COMMA_NUMBER_PATTERN
        normalised = func.replace(raw, ",", ".")
    else:
        pattern = DOT_NUMBER_PATTERN
        normalised = raw
    return case(
        (raw.op("~")(pattern), cast(normalised, Numeric)),
        else_=None,
    )


def is_empty_expression(session: Session, col: QueryableColumn) -> ColumnElement:
    if col.storage == "column":
        attr = getattr(ArticleSnapshotRow, col.column_attr)
        if col.type == "bool":
            return attr.is_(None)
        return attr == ""
    key = resolve_key(session, col)
    if key is None:
        raise ValueError(
            f"Die Spalte «{col.label_de}» ist in diesem Snapshot nicht vorhanden."
        )
    bp = _json_key_bind(key)
    if col.empty_encoding == "empty_string":
        return ArticleSnapshotRow.data[bp].astext == ""
    return not_(ArticleSnapshotRow.data.op("?")(bp))


def is_not_empty_expression(session: Session, col: QueryableColumn) -> ColumnElement:
    if col.storage == "column":
        attr = getattr(ArticleSnapshotRow, col.column_attr)
        if col.type == "bool":
            return attr.is_not(None)
        return attr != ""
    key = resolve_key(session, col)
    if key is None:
        raise ValueError(
            f"Die Spalte «{col.label_de}» ist in diesem Snapshot nicht vorhanden."
        )
    bp = _json_key_bind(key)
    if col.empty_encoding == "empty_string":
        return ArticleSnapshotRow.data[bp].astext != ""
    return ArticleSnapshotRow.data.op("?")(bp)


def hauptgruppe_code_expression() -> ColumnElement:
    number = ArticleSnapshotRow.article_number
    return case(
        (number.op("~")(CONFORMING_NUMBER_PATTERN), func.substr(number, 1, 3)),
        else_=None,
    )


def untergruppe_code_expression() -> ColumnElement:
    number = ArticleSnapshotRow.article_number
    return case(
        (number.op("~")(CONFORMING_NUMBER_PATTERN), func.substr(number, 5, 3)),
        else_=None,
    )


def select_values(session: Session, col: QueryableColumn) -> tuple[str, ...]:
    snapshot = _snapshot_for_catalog(session)
    if snapshot is None:
        return ()
    cache_key = (snapshot.id, col.name)
    now = time.monotonic()
    cached = _SELECT_CACHE.get(cache_key)
    if cached is not None and cached[0] > now:
        return cached[1]

    if col.storage == "column":
        expr = getattr(ArticleSnapshotRow, col.column_attr)
        stmt = (
            select(expr)
            .where(ArticleSnapshotRow.snapshot_id == snapshot.id)
            .distinct()
            .order_by(expr)
        )
        raw_values = [row[0] for row in session.execute(stmt).all()]
        if col.type == "bool":
            values: tuple[str, ...] = tuple(
                "Ja" if bool(v) else "Nein" for v in raw_values if v is not None
            )
        else:
            values = tuple(str(v) for v in raw_values if v not in (None, ""))
    else:
        key = resolve_key(session, col)
        if key is None:
            values = ()
        else:
            text_expr = ArticleSnapshotRow.data[_json_key_bind(key)].astext
            stmt = (
                select(text_expr)
                .where(
                    ArticleSnapshotRow.snapshot_id == snapshot.id,
                    is_not_empty_expression(session, col),
                )
                .distinct()
                .order_by(text_expr)
            )
            values = tuple(
                str(row[0]) for row in session.execute(stmt).all() if row[0] not in (None, "")
            )

    if col.name == "Gewichtseinheit":
        folded = {v.casefold() for v in values}
        if "kilogram" in folded or "kg" in folded:
            others = tuple(
                v for v in values if v.casefold() not in {"kilogram", "kg"}
            )
            values = ("kg", *others)

    _SELECT_CACHE[cache_key] = (now + SELECT_CACHE_TTL_SECONDS, values)
    return values


def verify_against_snapshot(session: Session, snapshot_id: uuid.UUID) -> list[str]:
    snapshot = session.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        return ["Snapshot nicht gefunden."]
    header = {str(col.get("key", "")) for col in (snapshot.columns or []) if isinstance(col, dict)}
    warnings: list[str] = []
    catalog_keys: set[str] = set()
    for col in COLUMNS:
        catalog_keys.add(col.name)
        catalog_keys.update(col.aliases)
        catalog_keys.add(col.label_de)
        if col.storage in ("column", "virtual"):
            continue
        if not any(key in header for key in col.json_keys):
            warnings.append(
                f"Katalogspalte «{col.label_de}» ist in diesem Snapshot nicht vorhanden."
            )
    for key in sorted(header):
        if key and key not in catalog_keys:
            warnings.append(f"Snapshot-Spalte «{key}» ist nicht im Katalog.")
    return warnings


def render_for_prompt(session: Session) -> str:
    lines: list[str] = []
    for col in COLUMNS:
        ops = ", ".join(op.value for op in col.allowed_operators)
        extra = ""
        if col.type == "select":
            values = select_values(session, col)
            extra = (
                " | Werte: " + " | ".join(f"«{value}»" for value in values)
                if values
                else " | Werte: (keine)"
            )
        lines.append(
            f"{col.name} | {col.type} | {col.label_de} | {col.description_de} | {ops}{extra}"
        )
    return "\n".join(lines)
