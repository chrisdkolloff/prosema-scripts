"""Create weclapp article categories for the group registry.

weclapp rejects nested parent+child on POST /articleCategory (unknown
properties ``children`` / ``articleCategories``). The pair is therefore two
POSTs in one function: parent first, then child with ``parentCategoryId``.

Writes run only from tools.prosema.ch in production — never from local or
any other host — because the configured tenant is the live weclapp instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.config import settings
from app.groups_service import GroupRegistryError
from scripts.weclapp.client import WeclappClient, WeclappError

TOOLS_HOST = "tools.prosema.ch"
CATEGORY_PATH = "/articleCategory"

MSG_PARENT_MISSING = "Hauptgruppe fehlt in weclapp — bitte zuerst die Hauptgruppe anlegen"
MSG_CREATE_FAILED = "Gruppe in weclapp konnte nicht angelegt werden"


def weclapp_category_writes_allowed(request: Request) -> bool:
    """True only for the public tools site in production."""
    if settings.environment != "production":
        return False
    host = (request.headers.get("host") or "").split(":", 1)[0].casefold()
    return host == TOOLS_HOST


def create_haupt_and_unter_in_weclapp(
    client: WeclappClient,
    *,
    haupt_name: str,
    haupt_code: str,
    unter_name: str,
    unter_code: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create Hauptgruppe and Untergruppe in weclapp, parent then child."""
    parent = client.post(
        CATEGORY_PATH,
        json={"name": haupt_name, "description": haupt_code},
    )
    if not isinstance(parent, dict) or not parent.get("id"):
        raise GroupRegistryError(MSG_CREATE_FAILED)
    try:
        child = client.post(
            CATEGORY_PATH,
            json={
                "name": unter_name,
                "description": unter_code,
                "parentCategoryId": parent["id"],
            },
        )
    except WeclappError:
        _delete_category(client, str(parent["id"]))
        raise
    if not isinstance(child, dict) or not child.get("id"):
        _delete_category(client, str(parent["id"]))
        raise GroupRegistryError(MSG_CREATE_FAILED)
    return parent, child


def create_unter_in_weclapp(
    client: WeclappClient,
    *,
    parent_name: str,
    unter_name: str,
    unter_code: str,
) -> dict[str, Any]:
    """Create an Untergruppe under an existing weclapp Hauptgruppe."""
    parent = _find_parent_category(client, parent_name)
    if parent is None:
        raise GroupRegistryError(MSG_PARENT_MISSING)
    child = client.post(
        CATEGORY_PATH,
        json={
            "name": unter_name,
            "description": unter_code,
            "parentCategoryId": parent["id"],
        },
    )
    if not isinstance(child, dict) or not child.get("id"):
        raise GroupRegistryError(MSG_CREATE_FAILED)
    return child


def _find_parent_category(client: WeclappClient, name: str) -> dict[str, Any] | None:
    needle = name.strip()
    for row in client.iter_pages("articleCategory"):
        if not isinstance(row, dict):
            continue
        if row.get("parentCategoryId"):
            continue
        if str(row.get("name") or "").strip() == needle:
            return row
    return None


def _delete_category(client: WeclappClient, category_id: str) -> None:
    if not category_id:
        return
    try:
        client.request("DELETE", f"{CATEGORY_PATH}/id/{category_id}")
    except WeclappError:
        return
