"""Create weclapp articles from the standardized import CSV template."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NUMBER_PLACEHOLDER = "wird autogeneriert"
GROUP_CODE_RE = re.compile(r"-\s*(\d+)\s*$")
RESTRICTED_SELECT_COLUMNS: tuple[str, ...] = (
    "Artikeltyp",
    "Einheit",
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
)


IMPORT_COLUMNS: tuple[str, ...] = (
    "Prosema Artikelnummer",
    "Lieferantenartikelnummer",
    "Hauptgruppe",
    "Untergruppe",
    "PROSEMA Kurztext",
    "PROSEMA Langtext",
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

LIST_CUSTOM_ATTRS: dict[str, str] = {
    "Hauptgruppe": "Hauptwarengruppe (Auswahl)",
    "Untergruppe": "Warengruppe (Auswahl)",
}

DEFAULTS: dict[str, str] = {
    "Prosema Artikelnummer": NUMBER_PLACEHOLDER,
    "Artikeltyp": "BASIC",
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


@dataclass
class ImportErrorRow:
    article_number: str
    message: str


@dataclass
class ImportStats:
    rows_read: int = 0
    created: int = 0
    skipped: int = 0
    errors: list[ImportErrorRow] = field(default_factory=list)
    created_ids: list[tuple[str, str]] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"Zeilen gelesen: {self.rows_read}",
            f"Erstellt:       {self.created}",
            f"Übersprungen:   {self.skipped}",
            f"Fehler:         {len(self.errors)}",
        ]
        for article_number, article_id in self.created_ids:
            lines.append(f"  OK {article_number} -> {article_id}")
        for error in self.errors:
            lines.append(f"  FEHLER {error.article_number}: {error.message}")
        return lines


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _load_schema() -> dict[str, Any]:
    from scripts.paths import DATA_DIR

    path = DATA_DIR / "weclapp_article_create_schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


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
    raw = _norm(row.get(column, ""))
    if raw:
        return raw
    return DEFAULTS.get(column, "")


class LookupTables:
    def __init__(self, schema: dict[str, Any]) -> None:
        lookups = schema.get("lookups") or {}
        self.units_by_key: dict[str, str] = {}
        self.unit_names: list[str] = []
        for unit in lookups.get("units") or []:
            unit_id = str(unit.get("id") or "")
            name = _norm(unit.get("name"))
            if name:
                self.unit_names.append(name)
            for key in (unit.get("name"), unit.get("description"), unit_id):
                text = _norm(key).lower()
                if text:
                    self.units_by_key[text] = unit_id
        self.unit_names = sorted(set(self.unit_names), key=str.lower)

        self.categories_by_name: dict[str, str] = {}
        self.category_names: list[str] = []
        for category in lookups.get("articleCategories") or []:
            name = _norm(category.get("name"))
            category_id = str(category.get("id") or "")
            if name and category_id:
                self.categories_by_name[name.lower()] = category_id
                self.category_names.append(name)
        self.category_names = sorted(set(self.category_names), key=str.lower)

        self.attrs_by_label: dict[str, dict[str, Any]] = {}
        for attr in lookups.get("customAttributes") or []:
            label = _norm(attr.get("label"))
            if label:
                self.attrs_by_label[label] = attr

    def unit_id(self, value: str) -> str:
        key = _norm(value).lower()
        if not key:
            raise ValueError("Einheit fehlt")
        unit_id = self.units_by_key.get(key)
        if not unit_id:
            raise ValueError(f"Unbekannte Einheit: {value}")
        return unit_id

    def category_id(self, value: str) -> str | None:
        key = _norm(value).lower()
        if not key:
            return None
        category_id = self.categories_by_name.get(key)
        if not category_id:
            raise ValueError(f"Unbekannte Kategorie: {value}")
        return category_id

    def list_value_id(self, attr_label: str, value: str) -> str:
        attr = self.attrs_by_label.get(attr_label)
        if not attr:
            raise ValueError(f"Zusatzfeld nicht gefunden: {attr_label}")
        wanted = _norm(value).lower()
        for option in attr.get("selectableValues") or []:
            option_value = _norm(option.get("value"))
            if option_value.lower() == wanted:
                return str(option.get("id"))
            prefix = option_value.split(" - ", 1)[0].lower()
            if prefix == wanted:
                return str(option.get("id"))
        raise ValueError(f"Ungültiger Wert für {attr_label}: {value}")

    def attr_id(self, label: str) -> str:
        attr = self.attrs_by_label.get(label)
        if not attr:
            raise ValueError(f"Zusatzfeld nicht gefunden: {label}")
        return str(attr.get("id"))

    def list_values(self, attr_label: str) -> list[str]:
        attr = self.attrs_by_label.get(attr_label) or {}
        values = [
            _norm(option.get("value"))
            for option in attr.get("selectableValues") or []
            if _norm(option.get("value"))
        ]
        return values


def dropdown_options(lookups: LookupTables | None = None) -> dict[str, list[str]]:
    lookups = lookups or LookupTables(_load_schema())
    schema = _load_schema()
    article_types = []
    tax_rates = []
    for item in schema.get("defaultedIfOmitted") or []:
        if item.get("field") == "articleType":
            article_types = list(item.get("allowed") or [])
        if item.get("field") == "taxRateType":
            tax_rates = list(item.get("allowed") or [])
    yes_no = ["Ja", "Nein"]
    return {
        "Artikeltyp": article_types,
        "Einheit": lookups.unit_names,
        "Kategorie": lookups.category_names,
        "Steuersatz": tax_rates,
        "Aktiv": yes_no,
        "Im Verkauf": yes_no,
        "Im Shop verfügbar": yes_no,
        "Im Shop aktiv": yes_no,
        "Bestand übertragen": yes_no,
        "Bodenleger": yes_no,
        "Dachdecker": yes_no,
        "Landschaftsgärtner": yes_no,
        "Plattenleger": yes_no,
        "Gewichtseinheit": ["kg", "g", "lb"],
        "Hauptgruppe": lookups.list_values("Hauptwarengruppe (Auswahl)"),
        "Untergruppe": lookups.list_values("Warengruppe (Auswahl)"),
    }


def parse_group_code(value: str, width: int) -> str | None:
    text = _norm(value)
    if not text:
        return None
    match = GROUP_CODE_RE.search(text)
    if not match:
        return None
    return f"{int(match.group(1)):0{width}d}"


def _master_path() -> Path:
    from scripts.paths import INPUT_DIR

    return INPUT_DIR / "input.xlsx"


def load_existing_running_numbers(master_path: Path | None = None) -> dict[tuple[str, str], int]:
    from core.numbering import Scheme

    scheme = Scheme()
    pattern = scheme.pattern()
    counters: dict[tuple[str, str], int] = {}
    path = master_path or _master_path()
    if not path.is_file():
        return counters

    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = sheet.iter_rows(min_row=1, values_only=True)
        try:
            headers = [str(value).strip() if value is not None else "" for value in next(rows)]
        except StopIteration:
            return counters
        try:
            article_idx = headers.index("Prosema Artikelnummer")
        except ValueError:
            return counters
        for values in rows:
            if article_idx >= len(values):
                continue
            value = values[article_idx]
            match = pattern.match(str(value).strip()) if value not in (None, "") else None
            if not match:
                continue
            key = (match.group(1), match.group(2))
            counters[key] = max(counters.get(key, 0), int(match.group(3)))
    finally:
        workbook.close()
    return counters


def generate_article_numbers(
    rows: list[dict[str, str]],
    *,
    master_path: Path | None = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    from core.numbering import Scheme

    scheme = Scheme()
    pattern = scheme.pattern()
    counters = load_existing_running_numbers(master_path)
    assigned = 0
    placeholders = 0
    kept = 0

    prepared: list[dict[str, str]] = []
    for row in rows:
        prepared.append(dict(row))

    for row in prepared:
        existing = _norm(row.get("Prosema Artikelnummer"))
        match = pattern.match(existing) if existing else None
        if not match:
            continue
        main = parse_group_code(row.get("Hauptgruppe", ""), scheme.main_width)
        sub = parse_group_code(row.get("Untergruppe", ""), scheme.sub_width)
        if main and sub and match.group(1) == main and match.group(2) == sub:
            key = (main, sub)
            counters[key] = max(counters.get(key, 0), int(match.group(3)))

    errors: list[str] = []
    for index, row in enumerate(prepared, start=2):
        main = parse_group_code(row.get("Hauptgruppe", ""), scheme.main_width)
        sub = parse_group_code(row.get("Untergruppe", ""), scheme.sub_width)
        supplier = _norm(row.get("Lieferantenartikelnummer")) or f"Zeile {index}"
        if not main or not sub:
            row["Prosema Artikelnummer"] = NUMBER_PLACEHOLDER
            placeholders += 1
            missing = []
            if not main:
                missing.append("Hauptgruppe")
            if not sub:
                missing.append("Untergruppe")
            errors.append(
                f"{supplier}: bitte { ' und '.join(missing) } ausfüllen, "
                "dann Artikelnummern erneut erzeugen."
            )
            continue

        existing = _norm(row.get("Prosema Artikelnummer"))
        match = pattern.match(existing) if existing else None
        if match and match.group(1) == main and match.group(2) == sub:
            kept += 1
            continue

        key = (main, sub)
        current = counters.get(key)
        nxt = scheme.start if current is None else current + scheme.step
        if nxt > scheme.max_running:
            raise OverflowError(
                f"Gruppe {main}.{sub} hat das Maximum überschritten."
            )
        counters[key] = nxt
        row["Prosema Artikelnummer"] = scheme.format(main, sub, nxt)
        assigned += 1

    return prepared, {
        "assigned": assigned,
        "kept": kept,
        "placeholders": placeholders,
        "errors": errors,
    }


def save_import_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMPORT_COLUMNS, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _norm(row.get(column, "")) for column in IMPORT_COLUMNS})


def validate_import_rows(rows: list[dict[str, str]]) -> list[ImportErrorRow]:
    lookups = LookupTables(_load_schema())
    errors: list[ImportErrorRow] = []
    seen: set[str] = set()
    for row in rows:
        article_number = _row_value(row, "Prosema Artikelnummer") or "(ohne Nummer)"
        try:
            payload = row_to_payload(row, lookups)
        except ValueError as exc:
            errors.append(ImportErrorRow(article_number, str(exc)))
            continue
        number = payload["articleNumber"]
        if number in seen:
            errors.append(ImportErrorRow(number, "Artikelnummer ist in der Datei doppelt"))
        seen.add(number)
    return errors


def row_to_payload(row: dict[str, str], lookups: LookupTables) -> dict[str, Any]:
    article_number = _row_value(row, "Prosema Artikelnummer")
    name = _row_value(row, "PROSEMA Kurztext")
    if not article_number or article_number == NUMBER_PLACEHOLDER:
        raise ValueError(
            "Prosema Artikelnummer fehlt. Bitte Hauptgruppe und Untergruppe setzen "
            "und Artikelnummern erzeugen."
        )
    if not name:
        raise ValueError("PROSEMA Kurztext fehlt")

    unit_value = _row_value(row, "Einheit")
    payload: dict[str, Any] = {
        "articleNumber": article_number,
        "name": name,
        "articleType": _row_value(row, "Artikeltyp").upper() or "BASIC",
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
    long_text = _row_value(row, "PROSEMA Langtext")
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
        custom_attributes.append(
            {
                "attributeDefinitionId": lookups.attr_id(label),
                "selectedValueId": lookups.list_value_id(label, value),
            }
        )

    if custom_attributes:
        payload["customAttributes"] = custom_attributes
    return payload


COLUMN_ALIASES = {
    "Artikelnr.": "Lieferantenartikelnummer",
    "Hauptwarengruppe": "Hauptgruppe",
    "Warengruppe": "Untergruppe",
}


def load_import_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if not reader.fieldnames:
            raise ValueError("CSV ohne Kopfzeile")
        missing = [column for column in ("PROSEMA Kurztext",) if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Pflichtspalten fehlen: {', '.join(missing)}")
        rows: list[dict[str, str]] = []
        for raw in reader:
            if not any(_norm(value) for value in raw.values()):
                continue
            normalized: dict[str, str] = {}
            for key, value in raw.items():
                target = COLUMN_ALIASES.get(key or "", key or "")
                text = _norm(value)
                if target and (target not in normalized or not normalized[target]):
                    normalized[target] = text
            row = {column: normalized.get(column, "") for column in IMPORT_COLUMNS}
            rows.append(row)
        return rows


def write_template(path: Path, *, include_dummy: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dummy = {
        "Prosema Artikelnummer": NUMBER_PLACEHOLDER,
        "Lieferantenartikelnummer": "TEST-SUP-001",
        "Hauptgruppe": "",
        "Untergruppe": "",
        "PROSEMA Kurztext": "TEST Dummy Artikel Import Pipeline",
        "PROSEMA Langtext": "Testdatensatz für den weclapp-Artikelimport. Kann gelöscht werden.",
        "Kurzbeschreibung": "TEST Dummy Artikel Import Pipeline",
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
        "Artikelbeschreibung HTML": "<p>Testdatensatz für den weclapp-Artikelimport.</p>",
        "Nettogewicht kg": "0.1",
        "Produkt-ID (Prosema)": "",
        "Varianten-ID (Prosema)": "",
    }
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMPORT_COLUMNS, delimiter=";")
        writer.writeheader()
        if include_dummy:
            writer.writerow(dummy)


def _article_exists(client, article_number: str) -> dict[str, Any] | None:
    data = client.get(
        "/article",
        params={"pageSize": 1, "articleNumber-eq": article_number},
    )
    rows = (data or {}).get("result") or []
    return rows[0] if rows else None


def import_articles(
    input_path: Path,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    article_numbers: set[str] | None = None,
) -> ImportStats:
    from scripts.weclapp.client import WeclappClient, WeclappError
    from scripts.weclapp.config import load_config

    lookups = LookupTables(_load_schema())
    rows = load_import_rows(input_path)
    if article_numbers is not None:
        rows = [row for row in rows if row.get("Prosema Artikelnummer") in article_numbers]
    if limit is not None:
        rows = rows[:limit]

    client = WeclappClient(load_config())
    stats = ImportStats(rows_read=len(rows))
    params = {"dryRun": "true"} if dry_run else None

    for row in rows:
        article_number = _row_value(row, "Prosema Artikelnummer") or "(ohne Nummer)"
        try:
            payload = row_to_payload(row, lookups)
            existing = _article_exists(client, payload["articleNumber"])
            if existing is not None:
                stats.skipped += 1
                stats.errors.append(
                    ImportErrorRow(
                        article_number,
                        f"existiert bereits (id={existing.get('id')})",
                    )
                )
                continue
            created = client.post("/article", params=params, json=payload)
            article_id = str((created or {}).get("id") or "")
            stats.created += 1
            stats.created_ids.append((payload["articleNumber"], article_id or "(dry-run)"))
        except WeclappError as exc:
            detail = exc.detail
            message = str(exc)
            if isinstance(detail, dict):
                message = str(detail.get("error") or detail.get("detail") or exc)
            stats.errors.append(ImportErrorRow(article_number, message))
        except ValueError as exc:
            stats.errors.append(ImportErrorRow(article_number, str(exc)))

    return stats


def run_job(params: dict):
    from gui.job_spec import RunResult, coerce_params, validate_params
    from scripts.paths import resolve_path

    params = coerce_params(JOB_SPEC, params)
    validate_params(JOB_SPEC, params)

    input_path = resolve_path(params["input"])
    dry_run = not bool(params.get("create"))
    try:
        stats = import_articles(input_path, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        return RunResult(summary=f"Fehler: {exc}", details=[])

    mode = "Dry-Run" if dry_run else "Import"
    return RunResult(
        summary=f"{mode}: {stats.created} erstellt, {len(stats.errors)} Fehler",
        details=stats.summary_lines(),
    )


def _build_job_spec():
    from gui.job_spec import FieldKind, FieldSpec, JobSpec

    return JobSpec(
        id="weclapp_import_articles",
        title="weclapp-Artikel anlegen",
        description=(
            "Liest die standardisierte Import-CSV und legt Artikel in weclapp an. "
            "Ohne Haken 'Wirklich anlegen' nur Dry-Run."
        ),
        fields=(
            FieldSpec(
                "input",
                "Import-CSV",
                FieldKind.FILE_IN,
                "data/weclapp_article_import_template.csv",
            ),
            FieldSpec(
                "create",
                "Wirklich anlegen (sonst nur prüfen)",
                FieldKind.BOOL,
                False,
            ),
        ),
        run=run_job,
    )


def main(argv: list[str] | None = None) -> int:
    _ensure_project_root()
    from scripts.paths import DATA_DIR, resolve_path

    parser = argparse.ArgumentParser(
        description="weclapp-Artikel aus der standardisierten Import-CSV anlegen.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_DIR / "weclapp_article_import_template.csv",
        help="Import-CSV (Semikolon, utf-8-sig)",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Artikel wirklich anlegen (sonst nur weclapp-Dry-Run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nur die ersten N Zeilen",
    )
    parser.add_argument(
        "--article",
        action="append",
        default=[],
        help="Nur diese Artikelnummer(n)",
    )
    parser.add_argument(
        "--write-template",
        action="store_true",
        help="Template-CSV schreiben und beenden",
    )
    args = parser.parse_args(argv)

    input_path = resolve_path(args.input)
    if args.write_template:
        write_template(input_path)
        print(f"Template geschrieben: {input_path}")
        return 0

    mode = "ANLEGEN" if args.create else "Dry-Run"
    print(f"Datei: {input_path}", file=sys.stderr)
    print(f"Modus: {mode}", file=sys.stderr)
    try:
        stats = import_articles(
            input_path,
            dry_run=not args.create,
            limit=args.limit,
            article_numbers=set(args.article) if args.article else None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    print("\nZusammenfassung", file=sys.stderr)
    for line in stats.summary_lines():
        print(f"  {line}", file=sys.stderr)
    return 0 if not stats.errors else 2


_ensure_project_root()
JOB_SPEC = _build_job_spec()


if __name__ == "__main__":
    raise SystemExit(main())
