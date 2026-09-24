"""Microsoft Graph helpers for SharePoint folder access (app-only)."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from azure.identity import ClientSecretCredential

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def graph_error_user_message(exc: GraphError) -> str:
    """Single-line explanation suitable for job status UI."""
    parts = [str(exc).strip()]
    if exc.status_code == 401:
        parts.append(
            "Microsoft hat den Zugriff abgelehnt. Einmal abmelden und erneut "
            "anmelden (SharePoint-Lesezugriff bestätigen). In Entra muss der "
            "App «Files.Read.All» (delegiert) mit Admin-Einwilligung hinterlegt sein."
        )
    elif exc.status_code == 403:
        parts.append(
            "Keine Berechtigung für diesen SharePoint-Ordner. Link prüfen oder "
            "IT um Zugriff auf «Files.Read.All» (delegiert) bitten."
        )
    detail = exc.detail
    if isinstance(detail, dict):
        err = detail.get("error")
        if isinstance(err, dict):
            inner = err.get("message") or err.get("code")
            if inner:
                parts.append(str(inner).strip())
        message = detail.get("message")
        if message:
            parts.append(str(message).strip())
    elif isinstance(detail, str) and detail.strip():
        parts.append(detail.strip())
    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        key = part.casefold()
        if key and key not in seen:
            seen.add(key)
            unique.append(part)
    return " — ".join(unique)


@dataclass(frozen=True)
class DriveItemRef:
    drive_id: str
    item_id: str
    name: str
    web_url: str | None = None


@dataclass(frozen=True)
class DriveFileEntry:
    name: str
    drive_id: str
    item_id: str
    size: int


def encode_sharing_url(url: str) -> str:
    """Encode a SharePoint sharing URL for the Graph ``/shares/{id}`` API."""
    encoded = base64.b64encode(url.strip().encode("utf-8")).decode("ascii")
    encoded = encoded.rstrip("=").replace("/", "_").replace("+", "-")
    return f"u!{encoded}"


def _credential() -> ClientSecretCredential:
    return ClientSecretCredential(
        settings.entra_tenant_id,
        settings.entra_client_id,
        settings.entra_client_secret,
    )


def get_graph_access_token() -> str:
    token = _credential().get_token(GRAPH_SCOPE)
    return token.token


def _graph_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _raise_for_status(response: httpx.Response, context: str) -> None:
    if response.status_code < 400:
        return
    detail: Any
    try:
        detail = response.json()
    except ValueError:
        detail = response.text[:500]
    raise GraphError(
        f"{context} ({response.status_code})",
        status_code=response.status_code,
        detail=detail,
    )


def resolve_sharepoint_folder_url(url: str, *, token: str | None = None) -> DriveItemRef:
    """Resolve a copied SharePoint folder link to drive + item ids."""
    raw = url.strip()
    if not raw:
        raise GraphError("SharePoint-Link fehlt.")

    token = token or get_graph_access_token()
    headers = _graph_headers(token)

    with httpx.Client(timeout=60.0) as client:
        if _looks_like_sharing_link(raw):
            share_id = encode_sharing_url(raw)
            response = client.get(
                f"{GRAPH_BASE}/shares/{share_id}/driveItem",
                headers=headers,
            )
            _raise_for_status(response, "SharePoint-Ordner konnte nicht geöffnet werden")
            item = response.json()
        else:
            item = _resolve_site_path_folder(client, headers, raw)

    parent = item.get("parentReference") or {}
    drive_id = str(parent.get("driveId") or "")
    item_id = str(item.get("id") or "")
    if not drive_id or not item_id:
        raise GraphError("SharePoint-Antwort ohne Laufwerk- oder Element-ID.", detail=item)
    if item.get("folder") is None:
        raise GraphError(
            "Der Link zeigt auf eine Datei, nicht auf einen Ordner.",
            detail={"name": item.get("name")},
        )
    return DriveItemRef(
        drive_id=drive_id,
        item_id=item_id,
        name=str(item.get("name") or ""),
        web_url=item.get("webUrl"),
    )


def _looks_like_sharing_link(url: str) -> bool:
    lowered = url.lower()
    return (
        ":u:" in lowered
        or ":f:" in lowered
        or ":x:" in lowered
        or "1drv.ms" in lowered
        or "sharepoint.com/:u" in lowered
    )


def _resolve_site_path_folder(
    client: httpx.Client,
    headers: dict[str, str],
    url: str,
) -> dict[str, Any]:
    parsed = urlparse(url)
    if "sharepoint.com" not in (parsed.netloc or "").lower():
        raise GraphError(
            "Unbekannter Link. Bitte in SharePoint «Link kopieren» für den Ordner verwenden."
        )
    hostname = parsed.netloc
    path = unquote(parsed.path or "")
    # /sites/SiteName/Shared Documents/rest/of/path
    parts = [segment for segment in path.split("/") if segment]
    if len(parts) < 2:
        raise GraphError("SharePoint-Pfad im Link ist zu kurz.", detail={"path": path})

    site_segment = parts[0]
    if site_segment not in {"sites", "teams"}:
        raise GraphError(
            "Nur Site- oder Team-Links werden unterstützt. «Link kopieren» ist zuverlässiger."
        )
    site_name = parts[1]
    remainder = parts[2:]
    if not remainder:
        raise GraphError("Im Link fehlt der Ordnerpfad nach dem Site-Namen.")

    site_path = f"/{site_segment}/{site_name}"
    site_resp = client.get(
        f"{GRAPH_BASE}/sites/{hostname}:{site_path}",
        headers=headers,
    )
    _raise_for_status(site_resp, "SharePoint-Site nicht gefunden")
    site_id = site_resp.json().get("id")
    if not site_id:
        raise GraphError("SharePoint-Site ohne ID.", detail=site_resp.json())

    # Graph expects path relative to default document library root.
    item_path = "/" + "/".join(remainder)
    item_resp = client.get(
        f"{GRAPH_BASE}/sites/{site_id}/drive/root:{item_path}",
        headers=headers,
    )
    _raise_for_status(item_resp, "Ordner im Dokumentenarchiv nicht gefunden")
    return item_resp.json()


def list_folder_files(
    folder: DriveItemRef,
    *,
    token: str | None = None,
    recursive: bool = False,
) -> list[DriveFileEntry]:
    """List image files in a SharePoint folder (non-recursive by default)."""
    token = token or get_graph_access_token()
    headers = _graph_headers(token)
    entries: list[DriveFileEntry] = []

    with httpx.Client(timeout=120.0) as client:
        if recursive:
            _walk_folder(client, headers, folder.drive_id, folder.item_id, entries)
        else:
            _list_one_level(client, headers, folder.drive_id, folder.item_id, entries)

    return entries


def _list_one_level(
    client: httpx.Client,
    headers: dict[str, str],
    drive_id: str,
    item_id: str,
    out: list[DriveFileEntry],
) -> None:
    url: str | None = (
        f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children"
        "?$select=id,name,size,file,folder"
    )
    while url:
        response = client.get(url, headers=headers)
        _raise_for_status(response, "Ordnerinhalt konnte nicht gelesen werden")
        payload = response.json()
        for node in payload.get("value") or []:
            if node.get("folder") is not None:
                continue
            if node.get("file") is None:
                continue
            name = str(node.get("name") or "")
            out.append(
                DriveFileEntry(
                    name=name,
                    drive_id=drive_id,
                    item_id=str(node.get("id") or ""),
                    size=int(node.get("size") or 0),
                )
            )
        url = payload.get("@odata.nextLink")


def _walk_folder(
    client: httpx.Client,
    headers: dict[str, str],
    drive_id: str,
    item_id: str,
    out: list[DriveFileEntry],
) -> None:
    url: str | None = (
        f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children"
        "?$select=id,name,size,file,folder"
    )
    while url:
        response = client.get(url, headers=headers)
        _raise_for_status(response, "Ordnerinhalt konnte nicht gelesen werden")
        payload = response.json()
        for node in payload.get("value") or []:
            child_id = str(node.get("id") or "")
            if node.get("folder") is not None:
                _walk_folder(client, headers, drive_id, child_id, out)
                continue
            if node.get("file") is None:
                continue
            out.append(
                DriveFileEntry(
                    name=str(node.get("name") or ""),
                    drive_id=drive_id,
                    item_id=child_id,
                    size=int(node.get("size") or 0),
                )
            )
        url = payload.get("@odata.nextLink")


def download_drive_item(
    entry: DriveFileEntry,
    *,
    token: str | None = None,
) -> bytes:
    token = token or get_graph_access_token()
    headers = _graph_headers(token)
    url = f"{GRAPH_BASE}/drives/{entry.drive_id}/items/{entry.item_id}/content"
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        _raise_for_status(response, f"Download fehlgeschlagen für {entry.name}")
        return response.content
