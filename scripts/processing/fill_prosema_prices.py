"""
Rabatte und Prosema-Preise in einem Weclapp-Export nachschlagen und berechnen.

Liest die Spalte „Rabattkategorie Lieferant“, füllt Rabatt 1 / Rabatt 2 aus
produktgruppen_rabatte.csv und berechnet:

  Einkaufspreis Prosema = UVP Lieferant × (1 − Rabatt1/100) × (1 − Rabatt2/100)
  Verkaufspreis Prosema (CHF) = Einkaufspreis Prosema × (1 + Zuschlag/100) × CONVERSION_RATE_EUR_CHF

Zuschlag ist fest 50 %. Währungen: UVP/Einkauf EUR, Verkauf CHF.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.export.generate_weclapp_import import load_discount_table
from scripts.paths import OUTPUT_EXPORT, PROJECT_ROOT, ensure_parent_dir, resolve_path

COL_ARTICLE = "Prosema-Artikelnummer"
COL_UVP = "UVP Lieferant"
COL_UVP_CURRENCY = "UVP Lieferant Währung"
COL_CATEGORY = "Rabattkategorie Lieferant"
COL_RABATT_1 = "Rabatt 1"
COL_RABATT_2 = "Rabatt 2"
COL_EK = "Einkaufspreis Prosema"
COL_EK_CURRENCY = "Einkaufspreis Prosema Währung"
COL_ZUSCHLAG = "Zuschlag (%)"
COL_VK = "Verkaufspreis Prosema"
COL_VK_CURRENCY = "Verkaufspreis Prosema Währung"

REQUIRED_COLUMNS = (
    COL_ARTICLE,
    COL_UVP,
    COL_UVP_CURRENCY,
    COL_CATEGORY,
    COL_RABATT_1,
    COL_RABATT_2,
    COL_EK,
    COL_EK_CURRENCY,
    COL_ZUSCHLAG,
    COL_VK,
    COL_VK_CURRENCY,
)

DEFAULT_ZUSCHLAG_PERCENT = 50
CURRENCY_EUR = "EUR"
CURRENCY_CHF = "CHF"
CONVERSION_RATE_EUR_CHF = 0.93

@dataclass
class FillStats:
    rows_read: int = 0
    rows_written: int = 0
    rows_priced: int = 0
    rows_without_category: int = 0
    rows_without_uvp: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"Zeilen gelesen:              {self.rows_read}",
            f"Zeilen geschrieben:          {self.rows_written}",
            f"  — davon mit Preis:         {self.rows_priced}",
            f"  — ohne Rabattkategorie:    {self.rows_without_category}",
            f"  — ohne UVP Lieferant:      {self.rows_without_uvp}",
        ]
        if self.warnings:
            lines.append(f"Warnungen:                   {len(self.warnings)}")
        return lines


def parse_money(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "–", "-", "—", "n/a", "N/A"}:
        return None
    text = text.replace("€", "").replace("CHF", "").replace("EUR", "")
    text = text.replace(" ", "").replace("'", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Ungültiger Preiswert: {value!r}") from exc


def format_percent(value: int) -> str:
    return str(value)


def format_money(value: float) -> str:
    return f"{value:.2f}"


def cumulative_purchase_price(uvp: float, rabatt1: int, rabatt2: int) -> float:
    return uvp * (1 - rabatt1 / 100) * (1 - rabatt2 / 100)


def sale_price_chf(
    einkaufspreis_eur: float,
    zuschlag_percent: int,
    *,
    eur_chf_rate: float = CONVERSION_RATE_EUR_CHF,
) -> float:
    vk_eur = einkaufspreis_eur * (1 + zuschlag_percent / 100)
    return vk_eur * eur_chf_rate


def _article_label(row: dict[str, str]) -> str:
    text = (row.get(COL_ARTICLE) or "").strip()
    return text or "(ohne Artikelnummer)"


def validate_discount_categories(
    rows: list[dict[str, str]],
    discounts: dict[str, tuple[int, int]],
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    unknown: dict[str, list[str]] = {}

    for row in rows:
        category = (row.get(COL_CATEGORY) or "").strip()
        if not category:
            warnings.append(
                f"{_article_label(row)} — keine Rabattkategorie in {COL_CATEGORY!r}"
            )
            continue
        if category not in discounts:
            unknown.setdefault(category, []).append(_article_label(row))

    errors: list[str] = []
    for category in sorted(unknown):
        articles = ", ".join(unknown[category])
        errors.append(
            f"Rabattkategorie {category!r} nicht in produktgruppen_rabatte.csv "
            f"(Artikel: {articles})"
        )
    return warnings, errors


def read_export_csv(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ";"
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError(f"CSV enthält keine Spaltenüberschriften: {path}")
        headers = list(reader.fieldnames)
        missing = [col for col in REQUIRED_COLUMNS if col not in headers]
        if missing:
            raise ValueError(
                f"Export-CSV fehlen Spalten: {', '.join(missing)} ({path})"
            )
        rows = [dict(row) for row in reader]
    return headers, rows, delimiter


def fill_prosema_prices(
    input_path: Path,
    rabatte_path: Path,
    output_path: Path,
    *,
    zuschlag_percent: int = DEFAULT_ZUSCHLAG_PERCENT,
) -> FillStats:
    headers, rows, delimiter = read_export_csv(input_path)
    discounts = load_discount_table(rabatte_path)

    category_warnings, category_errors = validate_discount_categories(rows, discounts)
    if category_errors:
        message = "Unbekannte Rabattkategorien:\n" + "\n".join(
            f"  {line}" for line in category_errors
        )
        raise ValueError(message)

    stats = FillStats(rows_read=len(rows), warnings=category_warnings)
    ensure_parent_dir(output_path)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=headers,
            delimiter=delimiter,
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in rows:
            out = dict(row)
            out[COL_UVP_CURRENCY] = CURRENCY_EUR
            out[COL_EK_CURRENCY] = CURRENCY_EUR
            out[COL_VK_CURRENCY] = CURRENCY_CHF
            out[COL_ZUSCHLAG] = format_percent(zuschlag_percent)

            category = (out.get(COL_CATEGORY) or "").strip()
            uvp = parse_money(out.get(COL_UVP))

            if not category:
                stats.rows_without_category += 1
                out[COL_RABATT_1] = ""
                out[COL_RABATT_2] = ""
                out[COL_EK] = ""
                out[COL_VK] = ""
            else:
                rabatt1, rabatt2 = discounts[category]
                out[COL_RABATT_1] = format_percent(rabatt1)
                out[COL_RABATT_2] = format_percent(rabatt2)

                if uvp is None:
                    stats.rows_without_uvp += 1
                    out[COL_EK] = ""
                    out[COL_VK] = ""
                else:
                    ek = round(
                        cumulative_purchase_price(uvp, rabatt1, rabatt2), 2
                    )
                    vk = round(sale_price_chf(ek, zuschlag_percent), 2)
                    out[COL_EK] = format_money(ek)
                    out[COL_VK] = format_money(vk)
                    stats.rows_priced += 1

            writer.writerow(out)
            stats.rows_written += 1

    return stats


def run_job(params: dict):
    from gui.job_spec import RunResult, coerce_params, validate_params

    params = coerce_params(JOB_SPEC, params)
    validate_params(JOB_SPEC, params)

    try:
        stats = fill_prosema_prices(
            resolve_path(params["input"]),
            resolve_path(params["rabatte"]),
            resolve_path(params["output"]),
            zuschlag_percent=int(params["zuschlag"]),
        )
    except PermissionError as exc:
        raise PermissionError(
            f"Konnte {params['output']} nicht speichern — ist die Datei geöffnet?"
        ) from exc

    details = stats.summary_lines()
    if stats.warnings:
        details.append("Warnung: Artikel ohne Rabattkategorie:")
        details.extend(f"  {warning}" for warning in stats.warnings)

    return RunResult(
        summary=f"Fertig: {params['output']}  ({stats.rows_priced} Preise berechnet)",
        details=details,
    )


def _build_job_spec():
    from gui.job_spec import FieldKind, FieldSpec, JobSpec

    return JobSpec(
        id="fill_prosema_prices",
        title="Prosema-Preise berechnen",
        description=(
            "Rabatte aus der Rabattkategorie nachschlagen und Einkaufs-/Verkaufspreise "
            "Prosema im Weclapp-Export berechnen."
        ),
        fields=(
            FieldSpec(
                "input",
                "Weclapp-Export",
                FieldKind.FILE_IN,
                "output/export/weclapp_export.csv",
            ),
            FieldSpec(
                "output",
                "Ausgabedatei",
                FieldKind.FILE_OUT,
                "output/export/weclapp_export_priced.csv",
                output_name="weclapp_export_priced.csv",
            ),
            FieldSpec(
                "rabatte",
                "Produktgruppen-Rabatte",
                FieldKind.FILE_IN,
                "data/produktgruppen_rabatte.csv",
                advanced=True,
            ),
            FieldSpec(
                "zuschlag",
                "Zuschlag (%)",
                FieldKind.INT,
                DEFAULT_ZUSCHLAG_PERCENT,
                advanced=True,
            ),
        ),
        run=run_job,
    )


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rabatte und Prosema-Preise im Weclapp-Export nachschlagen und berechnen."
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=str(OUTPUT_EXPORT / "weclapp_export.csv"),
        help="Weclapp-Export (.csv)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=str(OUTPUT_EXPORT / "weclapp_export_priced.csv"),
        help="Ausgabe-CSV mit berechneten Preisen",
    )
    parser.add_argument(
        "--rabatte",
        default=str(PROJECT_ROOT / "data" / "produktgruppen_rabatte.csv"),
        help="Produktgruppen-Rabatte (.csv)",
    )
    parser.add_argument(
        "--zuschlag",
        type=int,
        default=DEFAULT_ZUSCHLAG_PERCENT,
        help=f"Zuschlag in Prozent (Standard: {DEFAULT_ZUSCHLAG_PERCENT})",
    )
    return parser


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    rabatte_path = resolve_path(args.rabatte)

    for label, path in (
        ("Weclapp-Export", input_path),
        ("Rabattdatei", rabatte_path),
    ):
        if not path.exists():
            sys.exit(f"{label} nicht gefunden: {path}")

    try:
        stats = fill_prosema_prices(
            input_path,
            rabatte_path,
            output_path,
            zuschlag_percent=args.zuschlag,
        )
    except (ValueError, OSError) as exc:
        sys.exit(f"Abbruch: {exc}")

    if stats.warnings:
        print("Warnung: Artikel ohne Rabattkategorie:", file=sys.stderr)
        for warning in stats.warnings:
            print(f"  {warning}", file=sys.stderr)

    print(f"Fertig: {output_path}")
    for line in stats.summary_lines():
        print(line)


JOB_SPEC = _build_job_spec()


if __name__ == "__main__":
    main()
