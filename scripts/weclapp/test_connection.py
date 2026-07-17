"""Test weclapp API credentials and show a short data summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _project_root() -> Path:
    from scripts.paths import PROJECT_ROOT

    return PROJECT_ROOT


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def run_connection_test(
    *,
    tenant: str = "",
    api_token: str = "",
) -> dict[str, object]:
    from scripts.weclapp.client import WeclappClient, WeclappError
    from scripts.weclapp.config import load_config

    config = load_config(
        tenant=tenant or None,
        api_token=api_token or None,
    )
    client = WeclappClient(config)
    try:
        return client.test_connection()
    except WeclappError as exc:
        if exc.status_code == 401:
            raise ValueError(
                "Anmeldung fehlgeschlagen (401). Prüfe WECLAPP_API_TOKEN und "
                "ob der Token-Benutzer die nötigen Berechtigungen hat."
            ) from exc
        if exc.status_code == 403:
            raise ValueError(
                "Zugriff verweigert (403). Der API-Token-Benutzer hat nicht "
                "genug Berechtigungen in weclapp."
            ) from exc
        raise ValueError(str(exc)) from exc


def _format_summary(result: dict[str, object]) -> list[str]:
    sample = result.get("sample_currency")
    currency_name = ""
    if isinstance(sample, dict):
        currency_name = str(sample.get("name") or sample.get("id") or "")

    lines = [
        f"Tenant:     {result.get('tenant', '')}",
        f"API-URL:    {result.get('base_url', '')}",
        f"Artikel:    {result.get('article_count', '?')}",
        f"Parteien:   {result.get('party_count', '?')}",
    ]
    if currency_name:
        lines.append(f"Währung:    {currency_name} (Verbindung OK)")
    else:
        lines.append("Verbindung: OK")
    return lines


def run_job(params: dict):
    from gui.job_spec import RunResult, coerce_params, validate_params

    params = coerce_params(JOB_SPEC, params)
    validate_params(JOB_SPEC, params)

    try:
        result = run_connection_test(
            tenant=params.get("tenant", ""),
            api_token=params.get("api_token", ""),
        )
    except ValueError as exc:
        return RunResult(summary=f"Fehler: {exc}", details=[])

    return RunResult(
        summary="weclapp-Verbindung erfolgreich",
        details=_format_summary(result),
    )


def _build_job_spec():
    from gui.job_spec import FieldKind, FieldSpec, JobSpec

    return JobSpec(
        id="weclapp_test",
        title="weclapp-Verbindung testen",
        description=(
            "Prüft die weclapp-API-Zugangsdaten aus der Datei .env im Projektordner "
            "(WECLAPP_TENANT und WECLAPP_API_TOKEN). Optional können Tenant und Token "
            "unter Erweitert überschrieben werden."
        ),
        fields=(
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
    parser = argparse.ArgumentParser(
        description="weclapp-API-Verbindung testen.",
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

    try:
        result = run_connection_test(tenant=args.tenant, api_token=args.api_token)
    except ValueError as exc:
        sys.exit(f"Abbruch: {exc}")

    print("weclapp-Verbindung erfolgreich")
    for line in _format_summary(result):
        print(line)


_ensure_project_root()
JOB_SPEC = _build_job_spec()


if __name__ == "__main__":
    main()
