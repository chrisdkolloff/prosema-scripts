"""Group-registry diagram: SVG sunburst geometry, accordion, auth, no Plotly."""

from __future__ import annotations

import inspect
import math
import re
import uuid
from types import SimpleNamespace

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
from app.gruppen_diagram import (
    CHAR_W,
    INNER_FONT,
    INNER_R,
    OUTER_FONT,
    OUTER_R,
    build_sunburst_arcs,
    load_active_group_tree,
    max_chars_for,
)
from app.main import app
from app.models import Hauptgruppe

ACTOR = {"oid": "test-oid", "name": "Test User"}
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
):
    return create_untergruppe(db_session, parent, code=code, name=name, actor=ACTOR)


def _collapse_html(html: str, code: str) -> str:
    marker = f'id="collapse-{code}"'
    start = html.index(marker)
    rest = html[start:]
    end = rest.find("accordion-item")
    return rest if end < 0 else rest[:end]


def test_diagram_page_renders_accordion_and_lists_groups(user_client, db_session):
    parent = _make_hauptgruppe(db_session, name="DiagrammProbeHaupt")
    child = _make_untergruppe(db_session, parent, name="DiagrammProbeUnter")
    empty = _make_hauptgruppe(db_session, name="DiagrammProbeLeer")
    db_session.flush()

    response = user_client.get("/gruppen/diagramm")
    assert response.status_code == 200
    html = response.text
    assert "plotly" not in html.lower()
    assert 'src="/static/plotly.min.js"' not in html
    assert "cdn.plot.ly" not in html
    assert "cdn.jsdelivr" not in html
    assert "<h1 class=\"mb-3\">Gruppendiagramm</h1>" in html
    assert 'class="sunburst"' in html
    assert 'viewBox="0 0 720 720"' in html
    assert "textLength" not in html
    assert "lengthAdjust" not in html
    assert "sunburst-wrap" in html
    assert "<h2 class=\"h4 mb-3\">Alle Gruppen</h2>" in html
    assert 'id="gruppenAccordion"' in html
    assert "DiagrammProbeHaupt" in html
    assert "DiagrammProbeUnter" in html
    assert "DiagrammProbeLeer" in html
    assert "Keine Untergruppen" in html
    assert f'id="heading-{parent.code}"' in html
    assert f'id="collapse-{parent.code}"' in html
    assert f'id="heading-{empty.code}"' in html
    assert f'href="/gruppen/{parent.id}"' in html
    assert f'href="/gruppen/{parent.id}#untergruppe-{child.id}"' in html
    assert 'data-code="' in html
    assert f'data-name="{parent.name}"' in html
    assert f'data-name="{child.name}"' in html
    assert 'data-context="' in html
    assert 'id="sunburst-detail"' in html
    assert "/static/js/gruppen_diagramm.js" in html
    assert "gruppen-sub" in html
    assert "gruppen-acc-count" in html
    assert re.search(r">\s*1 Untergruppe\s*<", html)
    assert re.search(r">\s*0 Untergruppen\s*<", html)
    assert "<title>" not in html.split("<svg", 1)[1].split("</svg>", 1)[0]
    assert 'data-coreui-toggle="collapse"' in html
    assert 'data-coreui-parent="#gruppenAccordion"' in html
    assert 'class="badge bg-secondary me-2 gruppen-code"' in html
    assert 'class="badge bg-secondary me-3 gruppen-code"' in html
    tree = load_active_group_tree(db_session)
    n_unter = sum(len(children) for _, children in tree)
    haupt_word = "Hauptgruppe" if len(tree) == 1 else "Hauptgruppen"
    unter_word = "Untergruppe" if n_unter == 1 else "Untergruppen"
    assert f"{len(tree)} {haupt_word}" in html
    assert f"{n_unter} {unter_word}" in html
    assert f'aria-label="{len(tree)} {haupt_word}, {n_unter} {unter_word}"' in html
    assert "Keine Untergruppen" in _collapse_html(html, empty.code)
    assert 'href="/gruppen/diagramm"' in html
    assert 'href="/gruppen/diagramm">Diagramm</a>' in user_client.get("/gruppen").text
    assert "Die Sektorbreite entspricht" not in html
    assert "Haupt- und Untergruppen" not in html
    assert "getComputedTextLength" not in html

    asset = user_client.get("/static/plotly.min.js")
    assert asset.status_code == 404
    js = user_client.get("/static/js/gruppen_diagramm.js")
    assert js.status_code == 200
    assert b"data-code" in js.content


def test_diagram_sorts_groups_by_code(user_client, db_session):
    later = _make_hauptgruppe(db_session, code=_unused_code(db_session, "8"), name="Spaeter")
    earlier = _make_hauptgruppe(db_session, code=_unused_code(db_session, "7"), name="Frueher")
    _make_untergruppe(db_session, later, code="020", name="UnterSpaeter")
    _make_untergruppe(db_session, later, code="010", name="UnterFrueher")
    db_session.flush()

    html = user_client.get("/gruppen/diagramm").text
    headings = re.findall(r'id="heading-(\d{3})"', html)
    assert headings.index(earlier.code) < headings.index(later.code)
    later_body = html.split(f'id="collapse-{later.code}"', 1)[1]
    later_body = later_body.split("accordion-item", 1)[0]
    unter_codes = re.findall(r'gruppen-code">(\d{3})</span>', later_body)
    assert unter_codes == ["010", "020"]


def test_soft_deleted_groups_disappear_from_diagram(user_client, db_session):
    parent = _make_hauptgruppe(db_session, name="DiagrammLiveHaupt")
    _make_untergruppe(db_session, parent, code="010", name="DiagrammLiveUnter")
    gone = _make_untergruppe(db_session, parent, code="020", name="DiagrammGoneUnter")
    doomed = _make_hauptgruppe(db_session, name="DiagrammGoneHaupt")
    db_session.flush()

    before = user_client.get("/gruppen/diagramm")
    assert "DiagrammGoneUnter" in before.text
    assert "DiagrammGoneHaupt" in before.text
    assert "Keine Untergruppen" in _collapse_html(before.text, doomed.code)

    soft_delete_untergruppe(db_session, gone, actor=ACTOR)
    soft_delete_hauptgruppe(db_session, doomed, actor=ACTOR)
    db_session.flush()

    after = user_client.get("/gruppen/diagramm")
    assert after.status_code == 200
    assert "DiagrammLiveHaupt" in after.text
    assert "DiagrammLiveUnter" in after.text
    assert "DiagrammGoneUnter" not in after.text
    assert "DiagrammGoneHaupt" not in after.text
    assert f'id="heading-{doomed.code}"' not in after.text
    assert "Keine Untergruppen" not in _collapse_html(after.text, parent.code)


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


def _hg(code: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), code=code, name=name)


def _ug(code: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), code=code, name=name)


def test_inner_arc_angles_sum_to_two_pi():
    tree = [
        (_hg("010", "Zwei"), [_ug("010", "a"), _ug("020", "b")]),
        (_hg("020", "Eins"), [_ug("010", "c")]),
        (_hg("030", "Leer"), []),
    ]
    arcs = build_sunburst_arcs(tree)
    inner = [arc for arc in arcs if arc["ring"] == "inner"]
    assert len(inner) == 3
    assert math.isclose(sum(arc["a1"] - arc["a0"] for arc in inner), 2 * math.pi)


def test_empty_hauptgruppe_still_gets_a_nonzero_arc():
    tree = [
        (_hg("010", "Voll"), [_ug("010", "a"), _ug("020", "b")]),
        (_hg("020", "Leer"), []),
    ]
    arcs = build_sunburst_arcs(tree)
    empty = next(arc for arc in arcs if arc["code"] == "020" and arc["ring"] == "inner")
    assert empty["a1"] - empty["a0"] == pytest.approx(2 * math.pi / 3)
    assert empty["a1"] > empty["a0"]
    outer_codes = [arc["code"] for arc in arcs if arc["ring"] == "outer"]
    assert outer_codes == ["010", "020"]


def test_gruppen_diagram_module_does_not_import_plotly():
    source = inspect.getsource(inspect.getmodule(build_sunburst_arcs))
    assert "plotly" not in source


def test_outer_label_hidden_only_when_arc_is_too_narrow():
    wide = [(_hg("010", "Breit"), [_ug("010", "Nur eine")])]
    wide_outer = next(a for a in build_sunburst_arcs(wide) if a["ring"] == "outer")
    assert wide_outer["label_mode"] == "full"
    assert wide_outer["label"] == "010 Nur eine"
    assert wide_outer["text_anchor"] == "start"
    assert "textLength" not in str(wide_outer)

    medium_children = [_ug(f"{i:03d}", "x") for i in range(80)]
    medium = [(_hg("010", "Mittel"), medium_children)]
    medium_outer = next(a for a in build_sunburst_arcs(medium) if a["ring"] == "outer")
    assert medium_outer["show_label"] is True
    assert medium_outer["label"] == "000 x"

    narrow_children = [_ug(f"{i:03d}", "x") for i in range(150)]
    narrow = [(_hg("010", "Eng"), narrow_children)]
    narrow_outer = next(a for a in build_sunburst_arcs(narrow) if a["ring"] == "outer")
    assert narrow_outer["label_mode"] == "none"
    assert narrow_outer["show_label"] is False


def test_long_name_is_truncated_with_ellipsis_code_intact():
    long_name = "Abschlussprofile rund mit sehr langem Namen"
    tree = [(_hg("010", "Profil"), [_ug("010", long_name)])]
    outer = next(a for a in build_sunburst_arcs(tree) if a["ring"] == "outer")
    budget = max_chars_for(OUTER_R[0], OUTER_R[1], OUTER_FONT)
    keep = budget - len("010") - 2
    expected = f"010 {long_name[:keep].rstrip()}…"
    assert len(f"010 {long_name}") > budget
    assert keep >= 3
    assert outer["label_mode"] == "full"
    assert outer["label"] == expected
    assert outer["label"].startswith("010 ")
    assert outer["label"].endswith("…")
    assert not outer["label"].endswith(" …")
    assert "..." not in outer["label"]
    assert outer["code"] in outer["label"]
    assert outer["name"] == long_name
    assert outer["href"].endswith(f"#untergruppe-{tree[0][1][0].id}")


def test_truncation_strips_space_before_ellipsis():
    budget = max_chars_for(OUTER_R[0], OUTER_R[1], OUTER_FONT)
    keep = budget - len("010") - 2
    name = ("x" * (keep - 1)) + " extra words that continue"
    tree = [(_hg("010", "Profil"), [_ug("010", name)])]
    outer = next(a for a in build_sunburst_arcs(tree) if a["ring"] == "outer")
    assert outer["label"] == f"010 {'x' * (keep - 1)}…"
    assert not outer["label"].endswith(" …")
    assert outer["name"] == name


def test_label_falls_back_to_code_when_name_cannot_fit():
    from app.gruppen_diagram import _choose_label

    mode, label = _choose_label("010", "Langer Name", math.radians(10), *INNER_R, 80)
    assert mode == "full"
    assert label == "010"
    assert "…" not in label


def test_label_char_budget_follows_ring_depth():
    inner_budget = max_chars_for(INNER_R[0], INNER_R[1], INNER_FONT)
    outer_budget = max_chars_for(OUTER_R[0], OUTER_R[1], OUTER_FONT)
    assert inner_budget == int((125 - 8 - 10) / (INNER_FONT * CHAR_W))
    assert outer_budget == int((133 - 8 - 10) / (OUTER_FONT * CHAR_W))


def test_hauptgruppe_context_uses_singular():
    tree = [(_hg("010", "Solo"), [_ug("010", "Kind")])]
    inner = next(a for a in build_sunburst_arcs(tree) if a["ring"] == "inner")
    assert inner["context"] == "1 Untergruppe"
