"""Brand assets are served and wired into the layout and API docs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app

PLAIN_USER = {
    "oid": "user-oid",
    "name": "User",
    "email": "user@example.com",
    "roles": ["user"],
}

BRAND_PATHS = (
    "/static/brand/favicon.svg",
    "/static/brand/favicon.ico",
    "/static/brand/favicon-32.png",
    "/static/brand/apple-touch-icon.png",
    "/static/brand/logo-on-dark.png",
    "/static/brand/logo-on-light.png",
    "/static/brand/mark-on-dark.svg",
    "/static/brand/mark-on-light.svg",
)


def test_brand_assets_are_public():
    client = TestClient(app)
    for path in BRAND_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert len(response.content) > 200


def test_layout_includes_favicon_and_logos():
    app.dependency_overrides[get_current_user] = lambda: PLAIN_USER
    client = TestClient(app)
    try:
        html = client.get("/").text
    finally:
        app.dependency_overrides.clear()

    assert 'rel="icon"' in html
    assert 'rel="apple-touch-icon"' in html
    assert "/static/brand/favicon.svg" in html
    assert "/static/brand/favicon-32.png" in html
    assert 'rel="shortcut icon" href="/favicon.ico"' in html
    assert "/static/brand/logo-on-dark.png" in html
    assert "/static/brand/mark-on-dark.svg" in html
    assert "/static/brand/logo-on-light.png" in html
    assert "sidebar-brand-full" in html
    assert "sidebar-brand-narrow" in html
    assert 'aria-label="PROSEMA Tools"' in html
    assert 'class="nav-link header-account-link" href="/me"' in html
    assert 'href="https://prosemaag.sharepoint.com/sites/tools.prosema.ch"' in html
    assert 'target="_blank"' in html
    assert "FAQs" in html
    assert "Fragen zur Artikelliste" not in html
    css = client.get("/static/css/prosema.css").text
    assert "--cui-primary: var(--prosema-tools-blue)" in css
    assert "#1183c5" in css
    assert "#fc6f07" in css
    assert "td.highlight" in css
    assert "header-account-link" in css
    assert "table-layout: fixed" in css


def test_root_favicon_is_public():
    client = TestClient(app)
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert len(response.content) > 200
    svg = client.get("/static/brand/favicon.svg").text
    assert "#1183C5" in svg
    assert "#0e1215" in svg
    assert "#fc6f07" not in svg.lower()
    assert "<rect" not in svg


def test_docs_use_brand_favicon():
    client = TestClient(app)
    docs = client.get("/docs")
    redoc = client.get("/redoc")
    assert docs.status_code == 200
    assert redoc.status_code == 200
    assert "/static/brand/favicon.svg" in docs.text
    assert "/static/brand/favicon.svg" in redoc.text

