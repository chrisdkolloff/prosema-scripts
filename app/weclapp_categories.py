"""Create and rename weclapp article categories for the group registry.

weclapp rejects nested parent+child on POST /articleCategory (unknown
properties ``children`` / ``articleCategories``). The pair is therefore two
POSTs in one function: parent first, then child with ``parentCategoryId``.

Rename is PUT /articleCategory/id/{id}?ignoreMissingProperties=true with
``name`` (and ``version`` when weclapp sent one). A full PUT without that
flag fails because weclapp treats read-only fields such as ``createdDate``
as if they were submitted.

Writes run only from tools.prosema.ch in production — never from local or
any other host — because the configured tenant is the live weclapp instance.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from app.config import settings
from app.groups_service import CODE_RE, GroupRegistryError
from scripts.weclapp.client import WeclappClient, WeclappError

TOOLS_HOST = "tools.prosema.ch"
CATEGORY_PATH = "/articleCategory"

MSG_PARENT_MISSING = "Hauptgruppe fehlt in weclapp — bitte zuerst die Hauptgruppe anlegen"
MSG_CHILD_MISSING = "Untergruppe fehlt in weclapp"
MSG_CREATE_FAILED = "Gruppe in weclapp konnte nicht angelegt werden"
MSG_RENAME_FAILED = "Gruppe in weclapp konnte nicht umbenannt werden"
MSG_SYNC_BANNER = (
    "Tools und weclapp sind nicht synchron. Diese Einträge müssen manuell aktualisiert werden."
)


@dataclass(frozen=True)
class GroupSyncIssue:
    kind: str
    code: str
    message: str


def weclapp_category_writes_allowed(request: Request) -> bool:
    """True only for the public tools site in production."""
    if settings.environment != "production":
        return False
    host = (request.headers.get("host") or "").split(":", 1)[0].casefold()
    return host == TOOLS_HOST


def compare_group_registry(
    tools_haupt: Mapping[str, str],
    tools_unter: Mapping[tuple[str, str], str],
    categories: list[dict[str, Any]],
) -> list[GroupSyncIssue]:
    """Diff active Tools groups against weclapp article categories.

    Codes live in weclapp ``description``. Categories without a 3-digit code
    cannot be represented in Tools and are reported as needing a manual fix.
    """
    weclapp_haupt, weclapp_unter, uncoded = _weclapp_coded_tree(categories)
    issues: list[GroupSyncIssue] = []

    for code in sorted(set(tools_haupt) | set(weclapp_haupt)):
        tools_name = tools_haupt.get(code)
        weclapp_name = weclapp_haupt.get(code)
        if tools_name is None:
            issues.append(
                GroupSyncIssue(
                    "missing_in_tools",
                    code,
                    f"Hauptgruppe {code} {weclapp_name} fehlt in den Tools.",
                )
            )
        elif weclapp_name is None:
            issues.append(
                GroupSyncIssue(
                    "missing_in_weclapp",
                    code,
                    f"Hauptgruppe {code} {tools_name} fehlt in weclapp.",
                )
            )
        elif tools_name.strip() != weclapp_name.strip():
            issues.append(
                GroupSyncIssue(
                    "name_mismatch",
                    code,
                    (
                        f"Hauptgruppe {code}: Tools «{tools_name.strip()}», "
                        f"weclapp «{weclapp_name.strip()}»."
                    ),
                )
            )

    for key in sorted(set(tools_unter) | set(weclapp_unter)):
        label = f"{key[0]}.{key[1]}"
        tools_name = tools_unter.get(key)
        weclapp_name = weclapp_unter.get(key)
        if tools_name is None:
            issues.append(
                GroupSyncIssue(
                    "missing_in_tools",
                    label,
                    f"Untergruppe {label} {weclapp_name} fehlt in den Tools.",
                )
            )
        elif weclapp_name is None:
            issues.append(
                GroupSyncIssue(
                    "missing_in_weclapp",
                    label,
                    f"Untergruppe {label} {tools_name} fehlt in weclapp.",
                )
            )
        elif tools_name.strip() != weclapp_name.strip():
            issues.append(
                GroupSyncIssue(
                    "name_mismatch",
                    label,
                    (
                        f"Untergruppe {label}: Tools «{tools_name.strip()}», "
                        f"weclapp «{weclapp_name.strip()}»."
                    ),
                )
            )

    for parent_label, name in uncoded:
        where = f" (unter {parent_label})" if parent_label else ""
        issues.append(
            GroupSyncIssue(
                "uncoded_in_weclapp",
                "",
                (
                    f"weclapp-Kategorie «{name}»{where} hat keinen dreistelligen Code "
                    "— bitte in weclapp nachtragen oder entfernen."
                ),
            )
        )
    return issues


def collect_weclapp_sync_issues(
    client: WeclappClient,
    tools_haupt: Mapping[str, str],
    tools_unter: Mapping[tuple[str, str], str],
) -> list[GroupSyncIssue]:
    return compare_group_registry(tools_haupt, tools_unter, _categories(client))


def _is_group_code(value: object) -> bool:
    return bool(CODE_RE.fullmatch(str(value or "").strip()))


def _weclapp_coded_tree(
    categories: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[tuple[str, str], str], list[tuple[str, str]]]:
    by_id = {str(row.get("id") or ""): row for row in categories if isinstance(row, dict)}
    haupt: dict[str, str] = {}
    unter: dict[tuple[str, str], str] = {}
    uncoded: list[tuple[str, str]] = []
    for row in categories:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        desc = str(row.get("description") or "").strip()
        parent_id = str(row.get("parentCategoryId") or "")
        if not parent_id:
            if _is_group_code(desc):
                haupt[desc] = name
            elif name:
                uncoded.append(("", name))
            continue
        parent = by_id.get(parent_id) or {}
        parent_code = str(parent.get("description") or "").strip()
        parent_name = str(parent.get("name") or "").strip()
        parent_label = (
            f"{parent_code} {parent_name}".strip() if _is_group_code(parent_code) else parent_name
        )
        if _is_group_code(parent_code) and _is_group_code(desc):
            unter[(parent_code, desc)] = name
        elif name:
            uncoded.append((parent_label, name))
    return haupt, unter, uncoded


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


def rename_haupt_in_weclapp(
    client: WeclappClient,
    *,
    old_name: str,
    new_name: str,
    code: str,
) -> dict[str, Any]:
    """Rename a weclapp Hauptgruppe (parent article category)."""
    rows = _categories(client)
    found = _find_parent_category(rows, old_name, code=code)
    if found is None:
        already = _find_parent_category(rows, new_name, code=code)
        if already is not None and _name_eq(already, new_name):
            return already
        raise GroupRegistryError(MSG_PARENT_MISSING)
    return _put_category_name(client, found, new_name)


def rename_unter_in_weclapp(
    client: WeclappClient,
    *,
    parent_name: str,
    parent_code: str,
    old_name: str,
    new_name: str,
    unter_code: str,
) -> dict[str, Any]:
    """Rename a weclapp Untergruppe under its Hauptgruppe."""
    rows = _categories(client)
    parent = _find_parent_category(rows, parent_name, code=parent_code)
    if parent is None:
        raise GroupRegistryError(MSG_PARENT_MISSING)
    child = _find_child_category(rows, str(parent["id"]), old_name, code=unter_code)
    if child is None:
        already = _find_child_category(rows, str(parent["id"]), new_name, code=unter_code)
        if already is not None and _name_eq(already, new_name):
            return already
        raise GroupRegistryError(MSG_CHILD_MISSING)
    return _put_category_name(client, child, new_name)


def _categories(client: WeclappClient) -> list[dict[str, Any]]:
    return [row for row in client.iter_pages("articleCategory") if isinstance(row, dict)]


def _name_eq(row: dict[str, Any], name: str) -> bool:
    return str(row.get("name") or "").strip() == name.strip()


def _desc_eq(row: dict[str, Any], code: str) -> bool:
    return str(row.get("description") or "").strip() == code.strip()


def _find_parent_category(
    source: WeclappClient | list[dict[str, Any]],
    name: str,
    *,
    code: str | None = None,
) -> dict[str, Any] | None:
    rows = source if isinstance(source, list) else _categories(source)
    parents = [row for row in rows if not row.get("parentCategoryId")]
    for row in parents:
        if _name_eq(row, name):
            return row
    if code:
        by_code = [row for row in parents if _desc_eq(row, code)]
        if len(by_code) == 1:
            return by_code[0]
    return None


def _find_child_category(
    rows: list[dict[str, Any]],
    parent_id: str,
    name: str,
    *,
    code: str | None = None,
) -> dict[str, Any] | None:
    children = [row for row in rows if str(row.get("parentCategoryId") or "") == parent_id]
    for row in children:
        if _name_eq(row, name):
            return row
    if code:
        by_code = [row for row in children if _desc_eq(row, code)]
        if len(by_code) == 1:
            return by_code[0]
    return None


def _put_category_name(
    client: WeclappClient, row: dict[str, Any], new_name: str
) -> dict[str, Any]:
    category_id = str(row.get("id") or "")
    if not category_id:
        raise GroupRegistryError(MSG_RENAME_FAILED)
    payload: dict[str, Any] = {"name": new_name}
    if row.get("version") is not None:
        payload["version"] = row["version"]
    updated = client.put(
        f"{CATEGORY_PATH}/id/{category_id}",
        params={"ignoreMissingProperties": "true"},
        json=payload,
    )
    if updated is not None and not isinstance(updated, dict):
        raise GroupRegistryError(MSG_RENAME_FAILED)
    return updated if isinstance(updated, dict) else {**row, "name": new_name}


def _delete_category(client: WeclappClient, category_id: str) -> None:
    if not category_id:
        return
    try:
        client.request("DELETE", f"{CATEGORY_PATH}/id/{category_id}")
    except WeclappError:
        return
