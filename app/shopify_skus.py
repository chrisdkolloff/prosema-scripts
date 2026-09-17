"""Read-only Shopify variant SKU index. No write path."""

from __future__ import annotations

from scripts.shopify.client import ShopifyClient, ShopifyError
from scripts.shopify.config import load_config


def load_shopify_sku_set() -> set[str] | None:
    """Return all variant SKUs, or None if Shopify is not configured."""
    try:
        config = load_config()
    except (OSError, ValueError):
        return None
    if not config.access_token and not (config.client_id and config.client_secret):
        return None
    client = ShopifyClient(config)
    skus: set[str] = set()
    try:
        for product in client.iter_products():
            for variant in (product.get("variants") or {}).get("nodes") or []:
                if not isinstance(variant, dict):
                    continue
                sku = str(variant.get("sku") or "").strip()
                if sku:
                    skus.add(sku)
    except ShopifyError:
        return None
    return skus
