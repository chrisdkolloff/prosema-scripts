"""Load weclapp API credentials from environment or a .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from scripts.paths import PROJECT_ROOT


@dataclass(frozen=True)
class WeclappConfig:
    tenant: str
    api_token: str

    @property
    def base_url(self) -> str:
        tenant = self.tenant.strip().removesuffix(".weclapp.com")
        return f"https://{tenant}.weclapp.com/webapp/api/v2"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(
    *,
    tenant: str | None = None,
    api_token: str | None = None,
    env_file: Path | None = None,
) -> WeclappConfig:
    """Resolve credentials from arguments, then os.environ, then .env."""
    _load_dotenv(env_file or PROJECT_ROOT / ".env")

    resolved_tenant = (tenant or os.environ.get("WECLAPP_TENANT", "")).strip()
    resolved_token = (api_token or os.environ.get("WECLAPP_API_TOKEN", "")).strip()

    missing: list[str] = []
    if not resolved_tenant:
        missing.append("WECLAPP_TENANT")
    if not resolved_token:
        missing.append("WECLAPP_API_TOKEN")

    if missing:
        hint = (
            "Kopiere .env.example nach .env im Projektordner und trage "
            f"{', '.join(missing)} ein."
        )
        raise ValueError(f"weclapp-Zugangsdaten fehlen ({', '.join(missing)}). {hint}")

    return WeclappConfig(tenant=resolved_tenant, api_token=resolved_token)
