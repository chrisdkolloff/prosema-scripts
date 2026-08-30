"""weclapp article-category pair create: host guard and parent-then-child POSTs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from app.groups_service import GroupRegistryError
from app.weclapp_categories import (
    TOOLS_HOST,
    compare_group_registry,
    create_haupt_and_unter_in_weclapp,
    create_unter_in_weclapp,
    rename_haupt_in_weclapp,
    rename_unter_in_weclapp,
    weclapp_category_writes_allowed,
)
from scripts.weclapp.client import WeclappError


def _request(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/gruppen",
            "raw_path": b"/gruppen",
            "query_string": b"",
            "headers": [(b"host", host.encode("ascii"))],
            "client": ("127.0.0.1", 123),
            "server": (host, 443),
        }
    )


def test_writes_allowed_only_on_tools_host_in_production():
    with patch("app.weclapp_categories.settings") as settings:
        settings.environment = "production"
        assert weclapp_category_writes_allowed(_request(TOOLS_HOST)) is True
        assert weclapp_category_writes_allowed(_request("localhost")) is False
        assert weclapp_category_writes_allowed(
            _request("prosema-tools-prod.azurewebsites.net")
        ) is False

    with patch("app.weclapp_categories.settings") as settings:
        settings.environment = "local"
        assert weclapp_category_writes_allowed(_request(TOOLS_HOST)) is False


def test_create_pair_posts_parent_then_child():
    client = MagicMock()
    client.post.side_effect = [
        {"id": "p1", "name": "Zubehör"},
        {"id": "c1", "name": "Werkzeug"},
    ]

    parent, child = create_haupt_and_unter_in_weclapp(
        client,
        haupt_name="Zubehör",
        haupt_code="010",
        unter_name="Werkzeug",
        unter_code="030",
    )

    assert parent["id"] == "p1"
    assert child["id"] == "c1"
    assert client.post.call_count == 2
    first = client.post.call_args_list[0]
    second = client.post.call_args_list[1]
    assert first.args[0] == "/articleCategory"
    assert first.kwargs["json"] == {"name": "Zubehör", "description": "010"}
    assert "children" not in first.kwargs["json"]
    assert second.kwargs["json"] == {
        "name": "Werkzeug",
        "description": "030",
        "parentCategoryId": "p1",
    }


def test_create_pair_deletes_parent_if_child_fails():
    client = MagicMock()
    client.post.side_effect = [
        {"id": "p1", "name": "Zubehör"},
        WeclappError("child failed", status_code=400),
    ]

    with pytest.raises(WeclappError):
        create_haupt_and_unter_in_weclapp(
            client,
            haupt_name="Zubehör",
            haupt_code="010",
            unter_name="Werkzeug",
            unter_code="030",
        )

    client.request.assert_called_once_with("DELETE", "/articleCategory/id/p1")


def test_create_unter_requires_existing_parent():
    client = MagicMock()
    client.iter_pages.return_value = [
        {"id": "p1", "name": "Zubehör", "parentCategoryId": None},
    ]
    client.post.return_value = {"id": "c1"}

    child = create_unter_in_weclapp(
        client,
        parent_name="Zubehör",
        unter_name="Werkzeug",
        unter_code="030",
    )
    assert child["id"] == "c1"
    assert client.post.call_args.kwargs["json"]["parentCategoryId"] == "p1"

    client.iter_pages.return_value = []
    with pytest.raises(GroupRegistryError, match="fehlt in weclapp"):
        create_unter_in_weclapp(
            client,
            parent_name="Unbekannt",
            unter_name="X",
            unter_code="001",
        )


def test_rename_haupt_puts_name_with_ignore_missing():
    client = MagicMock()
    client.iter_pages.return_value = [
        {"id": "p1", "name": "Zubehör", "description": "010", "version": "3", "parentCategoryId": None},
    ]
    client.put.return_value = {"id": "p1", "name": "Zubehör neu"}

    updated = rename_haupt_in_weclapp(
        client,
        old_name="Zubehör",
        new_name="Zubehör neu",
        code="010",
    )
    assert updated["name"] == "Zubehör neu"
    client.put.assert_called_once_with(
        "/articleCategory/id/p1",
        params={"ignoreMissingProperties": "true"},
        json={"name": "Zubehör neu", "version": "3"},
    )


def test_rename_haupt_finds_parent_by_code_if_name_drifted():
    client = MagicMock()
    client.iter_pages.return_value = [
        {"id": "p1", "name": "Alt in weclapp", "description": "010", "version": "1"},
    ]
    client.put.return_value = {"id": "p1", "name": "Neu"}

    rename_haupt_in_weclapp(client, old_name="Zubehör", new_name="Neu", code="010")
    assert client.put.call_args.args[0] == "/articleCategory/id/p1"


def test_rename_haupt_missing_raises():
    client = MagicMock()
    client.iter_pages.return_value = []
    with pytest.raises(GroupRegistryError, match="fehlt in weclapp"):
        rename_haupt_in_weclapp(client, old_name="X", new_name="Y", code="999")


def test_rename_unter_puts_child():
    client = MagicMock()
    client.iter_pages.return_value = [
        {"id": "p1", "name": "Zubehör", "description": "010", "parentCategoryId": None},
        {
            "id": "c1",
            "name": "Werkzeug",
            "description": "030",
            "version": "2",
            "parentCategoryId": "p1",
        },
    ]
    client.put.return_value = {"id": "c1", "name": "Werkzeug neu"}

    rename_unter_in_weclapp(
        client,
        parent_name="Zubehör",
        parent_code="010",
        old_name="Werkzeug",
        new_name="Werkzeug neu",
        unter_code="030",
    )
    client.put.assert_called_once_with(
        "/articleCategory/id/c1",
        params={"ignoreMissingProperties": "true"},
        json={"name": "Werkzeug neu", "version": "2"},
    )


def test_rename_unter_missing_child_raises():
    client = MagicMock()
    client.iter_pages.return_value = [
        {"id": "p1", "name": "Zubehör", "description": "010", "parentCategoryId": None},
    ]
    with pytest.raises(GroupRegistryError, match="Untergruppe fehlt"):
        rename_unter_in_weclapp(
            client,
            parent_name="Zubehör",
            parent_code="010",
            old_name="Werkzeug",
            new_name="Neu",
            unter_code="030",
        )


def test_compare_group_registry_reports_manual_sync():
    tools_haupt = {"010": "Zubehör", "020": "Profile"}
    tools_unter = {("010", "030"): "Werkzeug", ("020", "010"): "Abschlussprofile rund"}
    categories = [
        {"id": "p1", "name": "Zubehör", "description": "010", "parentCategoryId": None},
        {
            "id": "c1",
            "name": "Werkzeug alt",
            "description": "030",
            "parentCategoryId": "p1",
        },
        {"id": "p2", "name": "Hilfsartikel", "description": "990", "parentCategoryId": None},
        {
            "id": "c2",
            "name": "Abschlussprofile (Messing)",
            "description": None,
            "parentCategoryId": "p1",
        },
    ]

    issues = compare_group_registry(tools_haupt, tools_unter, categories)
    kinds = {issue.kind for issue in issues}
    messages = " ".join(issue.message for issue in issues)

    assert "missing_in_weclapp" in kinds
    assert "missing_in_tools" in kinds
    assert "name_mismatch" in kinds
    assert "uncoded_in_weclapp" in kinds
    assert "Hauptgruppe 020 Profile fehlt in weclapp." in messages
    assert "Untergruppe 020.010 Abschlussprofile rund fehlt in weclapp." in messages
    assert "Hauptgruppe 990 Hilfsartikel fehlt in den Tools." in messages
    assert "Untergruppe 010.030: Tools «Werkzeug», weclapp «Werkzeug alt»." in messages
    assert "Abschlussprofile (Messing)" in messages
    assert "keinen dreistelligen Code" in messages


def test_compare_group_registry_in_sync_is_empty():
    tools_haupt = {"010": "Zubehör"}
    tools_unter = {("010", "030"): "Werkzeug"}
    categories = [
        {"id": "p1", "name": "Zubehör", "description": "010"},
        {"id": "c1", "name": "Werkzeug", "description": "030", "parentCategoryId": "p1"},
    ]
    assert compare_group_registry(tools_haupt, tools_unter, categories) == []
