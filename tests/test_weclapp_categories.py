"""weclapp article-category pair create: host guard and parent-then-child POSTs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from app.groups_service import GroupRegistryError
from app.weclapp_categories import (
    TOOLS_HOST,
    create_haupt_and_unter_in_weclapp,
    create_unter_in_weclapp,
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
