"""Export all weclapp articles to a local CSV snapshot."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExportStats:
    definitions_loaded: int = 0
    rows_written: int = 0
    columns: int = 0
    master_list_path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"Zusatzfeld-Definitionen: {self.definitions_loaded}",
            f"Artikel geschrieben:       {self.rows_written}",
            f"Spalten:                   {self.columns}",
        ]
        if self.master_list_path is not None:
            lines.append(f"Masterliste:               {self.master_list_path}")
        if self.warnings:
            lines.append(f"Warnungen:                 {len(self.warnings)}")
        return lines


def _project_root() -> Path:
    from scripts.paths import PROJECT_ROOT

    return PROJECT_ROOT


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _resolve_path(path: str | Path) -> Path:
    from scripts.paths import resolve_path

    return resolve_path(path)


def export_articles_csv(
    output_path: Path,
    *,
    tenant: str = "",
    api_token: str = "",
    active_only: bool = False,
) -> ExportStats:
    from scripts.weclapp.client import WeclappClient, WeclappError
    from scripts.weclapp.config import load_config
    from scripts.weclapp.master_columns import (
        EXPORT_COLUMNS,
        EXPORT_DISPLAY_COLUMNS,
        _format_ean,
        article_to_master_row,
        build_lookups,
        transform_export_rows,
        write_master_list_xlsx,
    )

    stats = ExportStats()
    config = load_config(tenant=tenant or None, api_token=api_token or None)
    client = WeclappClient(config)

    try:
        stats.definitions_loaded = client.get_count("customAttributeDefinition")
    except WeclappError:
        stats.warnings.append(
            "Zusatzfeld-Definitionen konnten nicht gezählt werden; Labels ggf. unvollständig."
        )

    params = {"active-eq": "true"} if active_only else None
    articles = list(client.iter_pages("article", params=params))
    lookups = build_lookups(client, articles)

    master_rows = [article_to_master_row(article, lookups) for article in articles]
    stats.rows_written = len(master_rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = output_path.with_name(f"{output_path.stem}_raw{output_path.suffix}")
    master_list_path = output_path.with_suffix(".xlsx")
    with open(raw_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(EXPORT_COLUMNS),
            delimiter=";",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in master_rows:
            if row.get("GTIN (EAN-Nummer)"):
                row["GTIN (EAN-Nummer)"] = _format_ean(row["GTIN (EAN-Nummer)"])
            writer.writerow(row)

    write_master_list_xlsx(master_rows, master_list_path)

    display_rows = transform_export_rows(master_rows)
    stats.columns = len(EXPORT_DISPLAY_COLUMNS)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(EXPORT_DISPLAY_COLUMNS),
            delimiter=";",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in display_rows:
            writer.writerow(row)

    stats.master_list_path = master_list_path
    return stats


def run_job(params: dict):
    from gui.job_spec import RunResult, coerce_params, validate_params

    params = coerce_params(JOB_SPEC, params)
    validate_params(JOB_SPEC, params)

    output_path = _resolve_path(params["output"])
    try:
        stats = export_articles_csv(
            output_path,
            tenant=params.get("tenant", ""),
            api_token=params.get("api_token", ""),
            active_only=bool(params.get("active_only")),
        )
    except ValueError as exc:
        return RunResult(summary=f"Fehler: {exc}", details=[])
    except OSError as exc:
        return RunResult(summary=f"Dateifehler: {exc}", details=[])

    details = stats.summary_lines()
    if stats.warnings:
        details.extend(f"  {warning}" for warning in stats.warnings)

    return RunResult(
        summary=f"Fertig: {output_path} ({stats.rows_written} Artikel)",
        details=details,
    )


def _build_job_spec():
    from gui.job_spec import FieldKind, FieldSpec, JobSpec

    return JobSpec(
        id="weclapp_export_articles",
        title="weclapp-Artikel exportieren",
        description=(
            "Lädt alle Artikel aus weclapp über die API und speichert sie als CSV-Snapshot "
            "(Rohdatei *_raw.csv mit Masterlisten-Spalten, Hauptdatei mit Import-Spaltennamen, "
            "Masterliste als .xlsx). "
            "Zugangsdaten werden aus .env gelesen."
        ),
        fields=(
            FieldSpec(
                "output",
                "Ausgabedatei",
                FieldKind.FILE_OUT,
                "output/export/weclapp_export.csv",
                output_name="weclapp_export.csv",
            ),
            FieldSpec(
                "active_only",
                "Nur aktive Artikel",
                FieldKind.BOOL,
                False,
                advanced=True,
            ),
            FieldSpec(
                "tenant",
                "Tenant (optional, sonst aus .env)",
                FieldKind.STR,
                "",
                advanced=True,
            ),
            FieldSpec(
                "api_token",
                "API-Token (optional, sonst aus .env)",
                FieldKind.STR,
                "",
                advanced=True,
            ),
        ),
        run=run_job,
    )


def build_argparser() -> argparse.ArgumentParser:
    root = _project_root()
    parser = argparse.ArgumentParser(
        description="weclapp-Artikel als CSV-Snapshot exportieren.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=str(root / "output" / "export" / "weclapp_export.csv"),
        help="Ausgabe-CSV",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Nur aktive Artikel exportieren",
    )
    parser.add_argument(
        "--tenant",
        default="",
        help="Tenant-Subdomain (sonst WECLAPP_TENANT aus .env)",
    )
    parser.add_argument(
        "--api-token",
        default="",
        help="API-Token (sonst WECLAPP_API_TOKEN aus .env)",
    )
    return parser


def main() -> None:
    _ensure_project_root()
    parser = build_argparser()
    args = parser.parse_args()

    output_path = Path(args.output)
    try:
        stats = export_articles_csv(
            output_path,
            tenant=args.tenant,
            api_token=args.api_token,
            active_only=args.active_only,
        )
    except ValueError as exc:
        sys.exit(f"Abbruch: {exc}")
    except OSError as exc:
        sys.exit(f"Dateifehler: {exc}")

    print(f"Fertig: {output_path} ({stats.rows_written} Artikel, {stats.columns} Spalten)")
    for line in stats.summary_lines():
        print(line)
    for warning in stats.warnings:
        print(f"Warnung: {warning}")


_ensure_project_root()
JOB_SPEC = _build_job_spec()


if __name__ == "__main__":
    main()
