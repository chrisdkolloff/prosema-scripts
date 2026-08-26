"""Group-registry sunburst: values, empty groups, auth, and local Plotly."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.groups_service import (
    create_hauptgruppe,
    create_untergruppe,
    soft_delete_hauptgruppe,
    soft_delete_untergruppe,
)
from app.gruppen_diagram import build_sunburst_figure, figure_html
from app.main import app
from app.models import Hauptgruppe, Untergruppe

ACTOR = {"oid": "test-oid", "name": "Test User"}
ADMIN_USER = {
    "oid": "admin-oid",
    "name": "Admin",
    "email": "admin@example.com",
    "roles": ["user", "admin"],
}
PLAIN_USER = {
    "oid": "user-oid",
    "name": "User",
    "email": "user@example.com",
    "roles": ["user"],
}


@pytest.fixture
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def user_client(db_session):
    def override_user():
        return PLAIN_USER

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def _unused_code(db_session, prefix: str = "9") -> str:
    used = {row[0] for row in db_session.execute(select(Hauptgruppe.code)).all()}
    for index in range(100):
        code = f"{prefix}{index:02d}"
        if code not in used:
            return code
    raise RuntimeError("No free test code remaining")


def _make_hauptgruppe(
    db_session, *, code: str | None = None, name: str = "Testhauptgruppe"
) -> Hauptgruppe:
    return create_hauptgruppe(
        db_session,
        code=code or _unused_code(db_session),
        name=name,
        actor=ACTOR,
    )


def _make_untergruppe(
    db_session,
    parent: Hauptgruppe,
    *,
    code: str = "001",
    name: str = "Testuntergruppe",
) -> Untergruppe:
    return create_untergruppe(db_session, parent, code=code, name=name, actor=ACTOR)


def _by_id(fig):
    trace = fig.data[0]
    return {
        node_id: {
            "label": label,
            "value": value,
            "parent": parent,
            "customdata": list(customdata),
            "shape": shape,
        }
        for node_id, label, value, parent, customdata, shape in zip(
            trace.ids,
            trace.labels,
            trace.values,
            trace.parents,
            trace.customdata,
            trace.marker.pattern.shape,
            strict=True,
        )
    }


def test_sunburst_values_come_from_child_lists():
    parent = Hauptgruppe(id=uuid.uuid4(), code="010", name="Profile")
    first = Untergruppe(
        id=uuid.uuid4(), hauptgruppe_id=parent.id, code="010", name="Abschlussprofile rund"
    )
    second = Untergruppe(id=uuid.uuid4(), hauptgruppe_id=parent.id, code="020", name="Winkel")
    empty = Hauptgruppe(id=uuid.uuid4(), code="020", name="Leergruppe")
    fig = build_sunburst_figure([(parent, [first, second]), (empty, [])])
    nodes = _by_id(fig)

    assert nodes[str(parent.id)]["value"] == 2
    assert nodes[str(first.id)]["value"] == 1
    assert nodes[str(second.id)]["value"] == 1
    assert nodes[str(empty.id)]["value"] == 1
    assert nodes["root"]["value"] == 3
    assert nodes[str(parent.id)]["label"] == "010 Profile"
    assert nodes[str(first.id)]["label"] == "010 Abschlussprofile rund"
    assert nodes[str(empty.id)]["label"] == "020 Leergruppe (leer)"
    assert nodes[str(empty.id)]["shape"] == "/"
    assert nodes[str(parent.id)]["shape"] == ""
    assert nodes[str(parent.id)]["customdata"] == [str(parent.id), "hauptgruppe", ""]
    assert nodes[str(first.id)]["customdata"] == [str(first.id), "untergruppe", str(parent.id)]


def test_sunburst_uses_light_fills_and_dark_labels():
    parent = Hauptgruppe(id=uuid.uuid4(), code="010", name="Profile")
    child = Untergruppe(
        id=uuid.uuid4(), hauptgruppe_id=parent.id, code="010", name="Abschlussprofile"
    )
    empty = Hauptgruppe(id=uuid.uuid4(), code="020", name="Leergruppe")
    fig = build_sunburst_figure([(parent, [child]), (empty, [])])
    trace = fig.data[0]
    fills = list(trace.marker.colors)
    assert fills[0] == "#e7e5e4"
    assert fills[1] == "#93c5fd"
    assert fills[2] == "#c0ddfe"
    assert fills[3] == "#d6d3d1"
    assert trace.insidetextfont.color == "#1c1917"


def test_figure_has_no_title():
    fig = build_sunburst_figure([])
    assert not fig.layout.title.text
    html = figure_html(fig)
    assert "Haupt- und Untergruppen" not in html


def test_figure_html_does_not_embed_cdn():
    parent = Hauptgruppe(id=uuid.uuid4(), code="010", name="Profile")
    html = figure_html(build_sunburst_figure([(parent, [])]))
    assert "cdn.plot.ly" not in html
    assert "https://" not in html
    assert 'id="gruppen-sunburst"' in html


def test_diagram_page_is_local_plotly_and_lists_groups(user_client, db_session):
    parent = _make_hauptgruppe(db_session, name="DiagrammProbeHaupt")
    child = _make_untergruppe(db_session, parent, name="DiagrammProbeUnter")
    _make_hauptgruppe(db_session, name="DiagrammProbeLeer")
    db_session.flush()

    response = user_client.get("/gruppen/diagramm")
    assert response.status_code == 200
    assert 'src="/static/plotly.min.js"' in response.text
    assert "cdn.plot.ly" not in response.text
    assert "cdn.jsdelivr" not in response.text
    assert "DiagrammProbeHaupt" in response.text
    assert "DiagrammProbeUnter" in response.text
    assert "DiagrammProbeLeer (leer)" in response.text
    assert str(parent.id) in response.text
    assert str(child.id) in response.text
    assert "hauptgruppe" in response.text
    assert "untergruppe" in response.text
    assert 'href="/gruppen/diagramm">Diagramm</a>' in response.text
    assert "Die Sektorbreite entspricht" not in response.text
    assert "Haupt- und Untergruppen" not in response.text
    assert "getComputedTextLength" in response.text

    asset = user_client.get("/static/plotly.min.js")
    assert asset.status_code == 200
    assert len(asset.content) > 1_000_000


def test_soft_deleted_groups_disappear_from_diagram(user_client, db_session):
    parent = _make_hauptgruppe(db_session, name="DiagrammLiveHaupt")
    kept = _make_untergruppe(db_session, parent, code="010", name="DiagrammLiveUnter")
    gone = _make_untergruppe(db_session, parent, code="020", name="DiagrammGoneUnter")
    doomed = _make_hauptgruppe(db_session, name="DiagrammGoneHaupt")
    db_session.flush()

    before = user_client.get("/gruppen/diagramm")
    assert "DiagrammGoneUnter" in before.text
    assert "DiagrammGoneHaupt (leer)" in before.text

    soft_delete_untergruppe(db_session, gone, actor=ACTOR)
    soft_delete_hauptgruppe(db_session, doomed, actor=ACTOR)
    db_session.flush()

    after = user_client.get("/gruppen/diagramm")
    assert after.status_code == 200
    assert "DiagrammLiveHaupt" in after.text
    assert "DiagrammLiveUnter" in after.text
    assert "DiagrammGoneUnter" not in after.text
    assert "DiagrammGoneHaupt" not in after.text
    assert str(kept.id) in after.text
    assert str(gone.id) not in after.text
    assert str(doomed.id) not in after.text


def test_diagram_requires_login():
    client = TestClient(app)
    response = client.get("/gruppen/diagramm", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"


def test_detail_rows_have_untergruppe_anchors(user_client, db_session):
    parent = _make_hauptgruppe(db_session, name="AnkerHaupt")
    child = _make_untergruppe(db_session, parent, name="AnkerUnter")
    db_session.flush()
    response = user_client.get(f"/gruppen/{parent.id}")
    assert response.status_code == 200
    assert f'id="untergruppe-{child.id}"' in response.text
