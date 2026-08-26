"""Minimal weclapp REST API v2 client."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import requests

from scripts.weclapp.config import WeclappConfig


class WeclappError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class WeclappClient:
    PAGE_SIZE = 1000
    MAX_RETRIES = 3

    def __init__(self, config: WeclappConfig, *, timeout: float = 30.0):
        self.config = config
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "AuthenticationToken": config.api_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    @property
    def base_url(self) -> str:
        return self.config.base_url

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params, doseq=True)}"
        return url

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = self._url(path, params)
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._session.request(
                    method,
                    url,
                    json=json,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 >= self.MAX_RETRIES:
                    raise WeclappError(f"Netzwerkfehler bei {method} {path}: {exc}") from exc
                time.sleep(1.0 * (attempt + 1))
                continue

            if response.status_code == 429 and attempt + 1 < self.MAX_RETRIES:
                time.sleep(1.0 * (attempt + 1))
                continue

            if response.status_code >= 400:
                detail: Any
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text
                raise WeclappError(
                    f"weclapp API Fehler {response.status_code} bei {method} {path}",
                    status_code=response.status_code,
                    detail=detail,
                )

            if response.status_code == 204 or not response.content:
                return None
            return response.json()

        raise WeclappError(f"Anfrage fehlgeschlagen: {last_error}")

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        return self.request("POST", path, params=params, json=json)

    def get_count(self, entity: str, *, params: dict[str, Any] | None = None) -> int:
        entity = entity.strip("/")
        data = self.get(f"/{entity}/count", params=params)
        if isinstance(data, dict):
            return int(data.get("result", 0))
        return int(data)

    def iter_pages(
        self,
        entity: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int | None = None,
    ):
        entity = entity.strip("/")
        page_size = page_size or self.PAGE_SIZE
        page = 1
        query = dict(params or {})
        query["pageSize"] = page_size

        while True:
            query["page"] = page
            payload = self.get(f"/{entity}", params=query)
            if not isinstance(payload, dict):
                break
            rows = payload.get("result") or []
            if not rows:
                break
            yield from rows
            if len(rows) < page_size:
                break
            page += 1

    def test_connection(self) -> dict[str, Any]:
        """Verify credentials and return a small summary."""
        currencies = self.get("/currency", params={"pageSize": 1})
        currency_rows = currencies.get("result", []) if isinstance(currencies, dict) else []
        return {
            "tenant": self.config.tenant,
            "base_url": self.base_url,
            "sample_currency": currency_rows[0] if currency_rows else None,
            "article_count": self.get_count("article"),
            "party_count": self.get_count("party"),
        }
