"""Template-driven Bezugsquellen CSV serialisation (web-app source of truth)."""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import DiscountCategory, ExportRow, ExportRun
from app.supply_export_fields import BY_KEY, FIELDS, FieldSpec, column_letter_index
from app.supply_exports import (
    WrittenColumn,
    current_discount_categories,
    extras_dict,
    export_discount_values,
    is_override,
    stored_field_text,
)
from scripts.export.generate_weclapp_import import (
    DISCOUNT_PRICE_TYPE,
    read_template_headers,
)
from scripts.paths import PROJECT_ROOT

TEMPLATE_CANDIDATES = (
    PROJECT_ROOT
    / "data"
    / "SupplySourcesWeclapp DemoImportfile_de (28.10.2024)(1).csv",
)

COL_NAME = "ARTIKELNAME"
COL_SUPPLIER_ARTICLE = "Lieferantenartikelnummer"
COL_SUPPLIER_NUMBER = "LIEFERANTENNUMMER"
COL_EK = "Bruttokaufpreis"
COL_DISC1_LABEL = "Zu- und Abschläge Bezeichnung 1"
COL_DISC1_TYPE = "Zu- und Abschläge Preisart 1"
COL_DISC1_VALUE = "Zu- und Abschläge Wert 1"
COL_DISC2_LABEL = "Zu- und Abschläge Bezeichnung 2"
COL_DISC2_TYPE = "Zu- und Abschläge Preisart 2"
COL_DISC2_VALUE = "Zu- und Abschläge Wert 2"
COL_CURRENCY = "Währung"
COL_UNIT = "Artikel-Mengeneinheit"
COL_MATCHCODE = "Matchcode"
COL_PRIMARY = "Primäre Bezugsquelle"
COL_DROPSHIP = "Dropshipping möglich"
COL_SALES_ARTICLE = "Verkaufsartikel-Nummer"
COL_SALES_PRICE = "Bruttopreis des zugehörigen Verkaufsartikels"
COL_SALES_CURRENCY = "Verkaufsartikel-Währung"
COL_PRICE_ENTRY = "Preis-Eintritt"


def resolve_template_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    for candidate in TEMPLATE_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Bezugsquellen-Importvorlage nicht gefunden unter data/")


def format_decimal_comma(value: Decimal | None) -> str:
    if value is None:
        return ""
    quantized = value.quantize(Decimal("0.01"))
    return f"{quantized:.2f}".replace(".", ",")


def format_percent_int(value: Decimal) -> str:
    return str(int(value))


def provenance_text(
    *,
    intent: str,
    category_code: str,
    percent: Decimal,
    registry: DiscountCategory | None,
    which: str,
    override_reason: str | None,
) -> str:
    if intent == "zero":
        base = f"Rabatt entfernt · explizit 0% · {which}"
        if override_reason:
            return f"{base} · {override_reason}"[:1000]
        return base[:1000]

    source = registry.source if registry else "Register"
    label = registry.label if registry and registry.label else category_code
    parts = [
        "Grundrabatt" if which == "D1" else "Kundenrabatt",
        source,
        f"Kat. {category_code}" if category_code else "ohne Kat.",
        f"{format_percent_int(percent)}%",
    ]
    if label and which == "D1":
        parts.insert(2, label)
    text = " · ".join(p for p in parts if p)
    if override_reason:
        text = f"{text} · Override: {override_reason}"
    return text[:1000]


def _serialise_stored(spec: FieldSpec, text: str) -> str:
    if not text:
        return ""
    if spec.input_kind in {"numeric", "percent"}:
        normalized = text.strip().replace("'", "").replace(" ", "").replace(",", ".")
        try:
            number = Decimal(normalized)
        except InvalidOperation:
            return text
        if spec.input_kind == "percent":
            return format_percent_int(number)
        return format_decimal_comma(number)
    return text


def csv_cell_value(
    spec: FieldSpec,
    row: ExportRow,
    registry: dict[str, DiscountCategory],
    run: ExportRun | None = None,
) -> str:
    """Raw value that would be written for this field, ignoring write_policy."""
    cat = registry.get(row.discount_category)
    d1, d2 = export_discount_values(row)
    reason = (
        row.override_reason
        if is_override(row, cat) or row.discount_intent == "zero"
        else None
    )
    if spec.field_key == "disc1_type":
        return DISCOUNT_PRICE_TYPE
    if spec.field_key == "disc2_type":
        return DISCOUNT_PRICE_TYPE
    if spec.field_key == "disc1_label":
        return provenance_text(
            intent=row.discount_intent,
            category_code=row.discount_category,
            percent=d1,
            registry=cat,
            which="D1",
            override_reason=reason,
        )
    if spec.field_key == "disc2_label":
        return provenance_text(
            intent=row.discount_intent,
            category_code=row.discount_category,
            percent=d2,
            registry=cat,
            which="D2",
            override_reason=reason,
        )
    source = run if run is not None else getattr(row, "run", None)
    if spec.field_key == "currency":
        return "EUR"
    if spec.field_key == "sales_currency":
        return (getattr(source, "sales_article_currency", None) or "").strip().upper()
    if spec.field_key == "sales_article_number":
        return (row.article_number or "").strip()
    if spec.field_key == "price_entry":
        day = getattr(source, "price_entry_date", None) if source is not None else None
        return day.strftime("%d.%m.%Y") if day else ""
    if spec.field_key == "base_discount_pct":
        return format_percent_int(d1)
    if spec.field_key == "customer_discount_pct":
        return format_percent_int(d2)
    if spec.field_key == "ek_price_before_discount":
        return format_decimal_comma(row.ek_price_before_discount)
    if spec.store == "extras":
        return _serialise_stored(spec, str(extras_dict(row).get(spec.field_key) or ""))
    if spec.store == "row":
        if spec.input_kind == "ja_nein":
            return stored_field_text(row, spec)
        if spec.input_kind in {"numeric", "percent"}:
            return _serialise_stored(spec, stored_field_text(row, spec))
        return stored_field_text(row, spec)
    return stored_field_text(row, spec)


def apply_write_policy(spec: FieldSpec, value: str) -> str:
    if spec.write_policy == "locked":
        return ""
    if spec.write_policy == "always":
        return value
    return value if str(value).strip() else ""


def _header_index_map(headers: list[str]) -> dict[str, int]:
    """Map weclapp column letter → header index, falling back to unique names."""
    by_letter: dict[str, int] = {}
    for spec in FIELDS:
        if not spec.weclapp_column:
            continue
        idx = column_letter_index(spec.weclapp_column)
        if 0 <= idx < len(headers):
            by_letter[spec.weclapp_column] = idx
    return by_letter


def build_csv_values(
    headers: list[str],
    row: ExportRow,
    registry: dict[str, DiscountCategory],
    run: ExportRun | None = None,
) -> list[str]:
    values = [""] * len(headers)
    index_by_letter = _header_index_map(headers)
    for spec in FIELDS:
        if not spec.weclapp_column:
            continue
        idx = index_by_letter.get(spec.weclapp_column)
        if idx is None:
            continue
        raw = csv_cell_value(spec, row, registry, run=run)
        values[idx] = apply_write_policy(spec, raw)
    return values


def build_csv_row(
    headers: list[str],
    row: ExportRow,
    registry: dict[str, DiscountCategory],
    run: ExportRun | None = None,
) -> dict[str, str]:
    values = build_csv_values(headers, row, registry, run=run)
    # Unique header names (tests). Duplicate labels such as Handelssprache
    # stay empty in phase 1; serialise uses the list, not this dict.
    return {header: value for header, value in zip(headers, values, strict=True)}


def sales_article_number_index(headers: list[str]) -> int:
    letter = BY_KEY["sales_article_number"].weclapp_column
    idx = _header_index_map(headers).get(letter)
    if idx is None:
        raise ValueError("Vorlage ohne Verkaufsartikel-Nummer (W).")
    return idx


def assert_sales_article_number_written(headers: list[str], values: list[str]) -> None:
    """Empty W on a row being written is a bug — the wizard invents a sales article from D."""
    idx = sales_article_number_index(headers)
    if not str(values[idx]).strip():
        raise ValueError("Verkaufsartikel-Nummer (W) darf nicht leer sein.")


def locked_write_violations(
    row: ExportRow,
    registry: dict[str, DiscountCategory],
    run: ExportRun | None = None,
) -> list[str]:
    """Locked export fields that have a stored value in extras (bug, not user error)."""
    found: list[str] = []
    extras = extras_dict(row)
    for key, value in extras.items():
        if not str(value or "").strip():
            continue
        spec = BY_KEY.get(str(key))
        if spec is None or spec.write_policy == "locked" or spec.store != "extras":
            label = spec.weclapp_column if spec and spec.weclapp_column else str(key)
            found.append(label)
    for spec in FIELDS:
        if spec.write_policy != "locked" or spec.store in {"article_context", "computed"}:
            continue
        if spec.store == "derived" and spec.field_key in extras and extras[spec.field_key]:
            found.append(spec.weclapp_column or spec.field_key)
        raw = csv_cell_value(spec, row, registry, run=run)
        if spec.store == "row" and str(raw).strip() and spec.weclapp_column:
            # Identity A/O are on_value, not locked. A locked row-store field with a
            # value that maps to a CSV column must not reach the writer.
            found.append(spec.weclapp_column)
    # de-dupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in found:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def written_column_counts(
    rows: list[ExportRow],
    registry: dict[str, DiscountCategory],
    run: ExportRun | None = None,
) -> list[WrittenColumn]:
    counts: list[WrittenColumn] = []
    for spec in FIELDS:
        if not spec.weclapp_column or spec.write_policy == "locked":
            continue
        n = 0
        for row in rows:
            value = apply_write_policy(spec, csv_cell_value(spec, row, registry, run=run))
            if spec.write_policy == "always" or str(value).strip():
                n += 1
        if n:
            counts.append(
                WrittenColumn(
                    field_key=spec.field_key,
                    label=spec.label_weclapp or spec.label_internal,
                    weclapp_column=spec.weclapp_column,
                    non_empty_count=n,
                )
            )
    return counts


def serialise_export_csv(
    db: Session,
    run: ExportRun,
    rows: list[ExportRow],
    *,
    template_path: Path | None = None,
) -> bytes:
    path = resolve_template_path(template_path)
    headers, encoding, delimiter, _has_bom = read_template_headers(path)
    registry = current_discount_categories(db, run.supplier_id)

    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer,
        delimiter=delimiter,
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\r\n",
    )
    writer.writerow(headers)
    for row in rows:
        violations = locked_write_violations(row, registry, run=run)
        if violations:
            raise ValueError(
                "Gesperrte Spalte würde geschrieben: " + ", ".join(violations)
            )
        values = build_csv_values(headers, row, registry, run=run)
        assert_sales_article_number_written(headers, values)
        writer.writerow(values)

    text = buffer.getvalue()
    try:
        return text.encode(encoding)
    except UnicodeEncodeError:
        return text.encode("cp1252", errors="replace")
