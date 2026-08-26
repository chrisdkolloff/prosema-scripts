"""Minimal Shopify Admin GraphQL client with client-credentials token refresh."""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from typing import Any

import requests

from scripts.shopify.config import ShopifyConfig


class ShopifyError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class ShopifyClient:
    MAX_RETRIES = 3

    def __init__(self, config: ShopifyConfig, *, timeout: float = 60.0):
        self.config = config
        self.timeout = timeout
        self._session = requests.Session()
        self._access_token = config.access_token
        if not self._access_token:
            self.refresh_access_token()
        self._apply_auth_headers()

    def _apply_auth_headers(self) -> None:
        self._session.headers.update(
            {
                "X-Shopify-Access-Token": self._access_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    @property
    def access_token(self) -> str:
        return self._access_token

    def refresh_access_token(self) -> str:
        if not self.config.client_id or not self.config.client_secret:
            raise ShopifyError(
                "Kein Access-Token und keine Client-Credentials zum Erneuern."
            )
        response = requests.post(
            self.config.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ShopifyError(
                f"Token-Anfrage fehlgeschlagen ({response.status_code})",
                status_code=response.status_code,
                detail=_safe_json(response),
            )
        payload = response.json()
        token = (payload.get("access_token") or "").strip()
        if not token:
            raise ShopifyError("Token-Antwort ohne access_token", detail=payload)
        self._access_token = token
        self._apply_auth_headers()
        return token

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if variables is not None:
            body["variables"] = variables

        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._session.post(
                    self.config.graphql_url,
                    json=body,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 >= self.MAX_RETRIES:
                    raise ShopifyError(f"Netzwerkfehler bei GraphQL: {exc}") from exc
                time.sleep(1.0 * (attempt + 1))
                continue

            if response.status_code == 401 and attempt == 0 and self.config.client_id:
                self.refresh_access_token()
                continue

            if response.status_code == 429 and attempt + 1 < self.MAX_RETRIES:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 1.0 * (attempt + 1)
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                raise ShopifyError(
                    f"Shopify API Fehler {response.status_code}",
                    status_code=response.status_code,
                    detail=_safe_json(response),
                )

            payload = response.json()
            if payload.get("errors"):
                # Throttle often arrives as GraphQL error extension
                if _is_throttled(payload) and attempt + 1 < self.MAX_RETRIES:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise ShopifyError("Shopify GraphQL Fehler", detail=payload["errors"])
            return payload.get("data") or {}

        raise ShopifyError(f"GraphQL-Anfrage fehlgeschlagen: {last_error}")

    def iter_products(self, *, page_size: int = 50):
        query = """
        query ProductsPage($first: Int!, $after: String) {
          products(first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id
                title
                handle
                status
                media(first: 20) {
                  nodes {
                    ... on MediaImage { id }
                    ... on Video { id }
                    ... on Model3d { id }
                    ... on ExternalVideo { id }
                  }
                }
                variants(first: 50) {
                  nodes { id sku barcode }
                }
              }
            }
          }
        }
        """
        after: str | None = None
        while True:
            data = self.graphql(
                query,
                {"first": page_size, "after": after},
            )
            connection = data.get("products") or {}
            for edge in connection.get("edges") or []:
                node = edge.get("node")
                if node:
                    yield node
            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break

    def iter_files(self, *, query: str = "", page_size: int = 50):
        """Iterate over files in Shopify's media library (Files API)."""
        gql = """
        query FilesPage($first: Int!, $after: String, $query: String) {
          files(first: $first, after: $after, query: $query) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                ... on MediaImage {
                  id
                  alt
                  image { url originalSrc }
                  createdAt
                }
                ... on GenericFile {
                  id
                  url
                  createdAt
                }
              }
            }
          }
        }
        """
        after: str | None = None
        while True:
            data = self.graphql(
                gql,
                {"first": page_size, "after": after, "query": query or None},
            )
            connection = data.get("files") or {}
            for edge in connection.get("edges") or []:
                node = edge.get("node")
                if node:
                    yield node
            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break

    def staged_upload_targets(
        self,
        files: list[Path],
    ) -> list[dict[str, Any]]:
        inputs = []
        for path in files:
            mime, _ = mimetypes.guess_type(path.name)
            inputs.append(
                {
                    "filename": path.name,
                    "mimeType": mime or "image/jpeg",
                    "httpMethod": "POST",
                    "resource": "PRODUCT_IMAGE",
                }
            )
        data = self.graphql(
            """
            mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
              stagedUploadsCreate(input: $input) {
                stagedTargets {
                  url
                  resourceUrl
                  parameters { name value }
                }
                userErrors { field message }
              }
            }
            """,
            {"input": inputs},
        )
        payload = data.get("stagedUploadsCreate") or {}
        errors = payload.get("userErrors") or []
        if errors:
            raise ShopifyError("stagedUploadsCreate fehlgeschlagen", detail=errors)
        targets = payload.get("stagedTargets") or []
        if len(targets) != len(files):
            raise ShopifyError(
                f"Erwartete {len(files)} Upload-Ziele, erhielt {len(targets)}"
            )
        return targets

    def upload_file_to_staged_target(
        self,
        path: Path,
        target: dict[str, Any],
    ) -> str:
        url = target["url"]
        resource_url = target["resourceUrl"]
        form: dict[str, str] = {
            item["name"]: item["value"] for item in (target.get("parameters") or [])
        }
        mime, _ = mimetypes.guess_type(path.name)
        with path.open("rb") as handle:
            response = requests.post(
                url,
                data=form,
                files={"file": (path.name, handle, mime or "image/jpeg")},
                timeout=self.timeout,
            )
        if response.status_code >= 400:
            raise ShopifyError(
                f"Datei-Upload fehlgeschlagen für {path.name} ({response.status_code})",
                status_code=response.status_code,
                detail=response.text[:500],
            )
        return resource_url

    def product_create_media(
        self,
        product_id: str,
        media: list[dict[str, str]],
    ) -> dict[str, Any]:
        data = self.graphql(
            """
            mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
              productCreateMedia(productId: $productId, media: $media) {
                media {
                  ... on MediaImage {
                    id
                    status
                    alt
                  }
                }
                mediaUserErrors { field message code }
              }
            }
            """,
            {"productId": product_id, "media": media},
        )
        payload = data.get("productCreateMedia") or {}
        errors = payload.get("mediaUserErrors") or []
        if errors:
            raise ShopifyError("productCreateMedia fehlgeschlagen", detail=errors)
        return payload


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _is_throttled(payload: dict[str, Any]) -> bool:
    for error in payload.get("errors") or []:
        extensions = error.get("extensions") or {}
        code = str(extensions.get("code") or "").upper()
        if code in {"THROTTLED", "MAX_COST_EXCEEDED"}:
            return True
        message = str(error.get("message") or "").lower()
        if "throttl" in message:
            return True
    return False
