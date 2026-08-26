"""Load Shopify API credentials from environment or a .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from scripts.paths import PROJECT_ROOT

DEFAULT_SHOP = "ym109q-ed"
DEFAULT_API_VERSION = "2025-10"


@dataclass(frozen=True)
class ShopifyConfig:
    shop: str
    client_id: str
    client_secret: str
    access_token: str
    api_version: str = DEFAULT_API_VERSION

    @property
    def shop_domain(self) -> str:
        shop = self.shop.strip()
        if shop.endswith(".myshopify.com"):
            return shop
        return f"{shop}.myshopify.com"

    @property
    def graphql_url(self) -> str:
        return (
            f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"
        )

    @property
    def token_url(self) -> str:
        return f"https://{self.shop_domain}/admin/oauth/access_token"


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
    shop: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    access_token: str | None = None,
    api_version: str | None = None,
    env_file: Path | None = None,
) -> ShopifyConfig:
    """Resolve credentials from arguments, then os.environ, then .env."""
    _load_dotenv(env_file or PROJECT_ROOT / ".env")

    resolved_shop = (shop or os.environ.get("SHOPIFY_SHOP", DEFAULT_SHOP)).strip()
    resolved_client_id = (
        client_id or os.environ.get("SHOPIFY_CLIENT_ID", "")
    ).strip()
    resolved_client_secret = (
        client_secret or os.environ.get("SHOPIFY_CLIENT_SECRET", "")
    ).strip()
    resolved_token = (
        access_token or os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    ).strip()
    resolved_version = (
        api_version or os.environ.get("SHOPIFY_API_VERSION", DEFAULT_API_VERSION)
    ).strip() or DEFAULT_API_VERSION

    if not resolved_shop:
        raise ValueError(
            "Shopify-Shop fehlt (SHOPIFY_SHOP, z. B. ym109q-ed)."
        )

    if not resolved_token and not (resolved_client_id and resolved_client_secret):
        raise ValueError(
            "Shopify-Zugangsdaten fehlen. Setze SHOPIFY_ACCESS_TOKEN oder "
            "SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET in .env."
        )

    return ShopifyConfig(
        shop=resolved_shop,
        client_id=resolved_client_id,
        client_secret=resolved_client_secret,
        access_token=resolved_token,
        api_version=resolved_version,
    )
