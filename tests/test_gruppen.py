"""Group registry: database constraints, resolution, and seeding."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import engine, get_db
from app.groups_service import (
    AmbiguousGroupMatch,
    add_alias,
    create_hauptgruppe,
    create_hauptgruppe_with_untergruppe,
    create_untergruppe,
    normalize_alias,
    resolve_hauptgruppe,
    resolve_untergruppe,
)
from app.main import app
from app.models import Hauptgruppe, Untergruppe
from scripts.seed_groups import apply_seed, main, parse_workbook

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
def admin_client(db_session):
    def override_user():
        return ADMIN_USER

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


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


def _write_workbook(
    path: Path,
    *,
    hauptgruppen: list[tuple[str, str]],
    untergruppen: list[tuple[str, str, str]],
) -> Path:
    wb = Workbook()
    ws_main = wb.active
    ws_main.title = "Hauptgruppen"
    ws_main.append(["Code", "Bezeichnung"])
    for code, name in hauptgruppen:
        ws_main.append([code, name])
    ws_sub = wb.create_sheet("Untergruppen")
    ws_sub.append(["Hauptgruppe", "Untergruppe", "Bezeichnung"])
    for main_code, sub, name in untergruppen:
        ws_sub.append([main_code, sub, name])
    wb.save(path)
    return path


def test_rename_locked_group_succeeds(db_session):
    group = _make_hauptgruppe(db_session, name="Alt")
    group.locked_at = datetime.now(UTC)
    db_session.flush()
    group.name = "Neu"
    db_session.flush()
    db_session.refresh(group)
    assert group.name == "Neu"


def test_changing_locked_group_code_raises(db_session):
    group = _make_hauptgruppe(db_session)
    group.locked_at = datetime.now(UTC)
    db_session.flush()
    group.code = _unused_code(db_session, prefix="8")
    with pytest.raises(DBAPIError, match="group code is locked"):
        db_session.flush()


def test_changing_locked_untergruppe_parent_raises(db_session):
    parent = _make_hauptgruppe(db_session)
    other = _make_hauptgruppe(db_session, name="Andere")
    child = _make_untergruppe(db_session, parent)
    child.locked_at = datetime.now(UTC)
    db_session.flush()
    child.hauptgruppe_id = other.id
    with pytest.raises(DBAPIError, match="group parent is locked"):
        db_session.flush()


def test_raw_delete_raises(db_session):
    parent = _make_hauptgruppe(db_session)
    child = _make_untergruppe(db_session, parent)
    child_id = child.id
    parent_id = parent.id

    nested = db_session.begin_nested()
    with pytest.raises(DBAPIError, match="hard delete of groups is forbidden"):
        db_session.execute(delete(Untergruppe).where(Untergruppe.id == child_id))
        db_session.flush()
    nested.rollback()

    nested = db_session.begin_nested()
    with pytest.raises(DBAPIError, match="hard delete of groups is forbidden"):
        db_session.execute(delete(Hauptgruppe).where(Hauptgruppe.id == parent_id))
        db_session.flush()
    nested.rollback()


def test_soft_delete_hauptgruppe_with_live_untergruppen(db_session):
    parent = _make_hauptgruppe(db_session)
    child = _make_untergruppe(db_session, parent)

    nested = db_session.begin_nested()
    parent.deleted_at = datetime.now(UTC)
    with pytest.raises(DBAPIError, match="cannot soft-delete hauptgruppe with live untergruppen"):
        db_session.flush()
    nested.rollback()

    db_session.refresh(parent)
    db_session.refresh(child)
    assert parent.deleted_at is None
    child.deleted_at = datetime.now(UTC)
    db_session.flush()
    parent.deleted_at = datetime.now(UTC)
    db_session.flush()
    db_session.refresh(parent)
    assert parent.deleted_at is not None


def test_clearing_locked_at_raises(db_session):
    group = _make_hauptgruppe(db_session)
    group.locked_at = datetime.now(UTC)
    db_session.flush()
    group.locked_at = None
    with pytest.raises(DBAPIError, match="locked_at cannot be cleared"):
        db_session.flush()


def test_live_codes_unique_deleted_does_not_block(db_session):
    first = _make_hauptgruppe(db_session, name="Erste")
    code = first.code

    nested = db_session.begin_nested()
    db_session.add(Hauptgruppe(code=code, name="Zweite"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    nested.rollback()

    first.deleted_at = datetime.now(UTC)
    db_session.flush()
    reused = create_hauptgruppe(db_session, code=code, name="Wiederverwendet", actor=ACTOR)
    db_session.flush()
    assert reused.code == code
    assert reused.id != first.id


def test_normalize_alias():
    assert normalize_alias("fliesenprofile") == "FLIESENPROFILE"
    assert normalize_alias("  Fliesen   Profile  ") == "FLIESEN PROFILE"
    assert normalize_alias("\tBalkon - Terrasse\n") == "BALKON - TERRASSE"


def test_resolve_hauptgruppe(db_session):
    group = _make_hauptgruppe(db_session, name="Auflösungstest")
    add_alias(db_session, alias="ALTNAME", actor=ACTOR, hauptgruppe=group)
    db_session.flush()

    assert resolve_hauptgruppe(db_session, group.code).id == group.id
    assert resolve_hauptgruppe(db_session, "Auflösungstest").id == group.id
    assert resolve_hauptgruppe(db_session, "altname").id == group.id
    assert resolve_hauptgruppe(db_session, "gibt-es-nicht") is None

    _make_hauptgruppe(db_session, name="Auflösungstest")
    db_session.flush()
    with pytest.raises(AmbiguousGroupMatch):
        resolve_hauptgruppe(db_session, "Auflösungstest")

    child = _make_untergruppe(db_session, group, name="Kind")
    add_alias(db_session, alias="ALTKIND", actor=ACTOR, untergruppe=child)
    db_session.flush()
    assert resolve_untergruppe(db_session, group, child.code).id == child.id
    assert resolve_untergruppe(db_session, group, "Kind").id == child.id
    assert resolve_untergruppe(db_session, group, "altkind").id == child.id
    assert resolve_untergruppe(db_session, group, "fehlt") is None


def test_seeding_twice_inserts_nothing_the_second_time(db_session, tmp_path):
    code = _unused_code(db_session)
    path = _write_workbook(
        tmp_path / "gruppen.xlsx",
        hauptgruppen=[(code, "Seedhaupt")],
        untergruppen=[(code, "010", "Seedunter")],
    )
    plan = parse_workbook(path)
    apply_seed(db_session, plan)
    db_session.flush()
    assert plan.haupt_inserted == 1
    assert plan.unter_inserted == 1

    again = parse_workbook(path)
    apply_seed(db_session, again)
    db_session.flush()
    assert again.haupt_inserted == 0
    assert again.unter_inserted == 0
    assert again.haupt_present == 1
    assert again.unter_present == 1


def test_seeding_duplicate_code_exits_nonzero_and_commits_nothing(db_session, tmp_path):
    code = _unused_code(db_session)
    path = _write_workbook(
        tmp_path / "dup.xlsx",
        hauptgruppen=[(code, "Eins"), (code, "Zwei")],
        untergruppen=[],
    )
    plan = parse_workbook(path)
    assert plan.rejected
    apply_seed(db_session, plan)
    db_session.flush()
    found = db_session.scalars(select(Hauptgruppe).where(Hauptgruppe.code == code)).all()
    assert found == []
    assert main(["--file", str(path)]) == 1
    still = db_session.scalars(select(Hauptgruppe).where(Hauptgruppe.code == code)).all()
    assert still == []


def test_locked_code_change_returns_german_error_page(admin_client, db_session):
    group = _make_hauptgruppe(db_session)
    group.locked_at = datetime.now(UTC)
    db_session.flush()
    response = admin_client.post(
        f"/gruppen/{group.id}/code",
        data={"code": _unused_code(db_session, prefix="8")},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Es befinden sich bereits Artikel in dieser Hauptgruppe" in response.text
    assert "Traceback" not in response.text


def test_non_admin_writes_return_403(user_client, db_session):
    group = _make_hauptgruppe(db_session)
    db_session.flush()
    assert user_client.get("/gruppen").status_code == 200
    assert user_client.post(
        "/gruppen",
        data={
            "code": "777",
            "name": "X",
            "unter_code": "001",
            "unter_name": "Y",
        },
        follow_redirects=False,
    ).status_code == 403
    assert user_client.post(
        f"/gruppen/{group.id}/umbenennen",
        data={"name": "Y"},
        follow_redirects=False,
    ).status_code == 403
    assert user_client.post(
        f"/gruppen/{group.id}/loeschen",
        follow_redirects=False,
    ).status_code == 403


def test_create_pair_locally_skips_weclapp(admin_client, db_session):
    code = _unused_code(db_session)
    with patch("app.routes.gruppen.weclapp_client_for") as mock_client:
        response = admin_client.post(
            "/gruppen",
            data={
                "code": code,
                "name": "Lokalhaupt",
                "unter_code": "001",
                "unter_name": "Lokalunter",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    mock_client.assert_not_called()
    parent = db_session.scalars(select(Hauptgruppe).where(Hauptgruppe.code == code)).one()
    assert parent.name == "Lokalhaupt"
    kids = list(
        db_session.scalars(select(Untergruppe).where(Untergruppe.hauptgruppe_id == parent.id))
    )
    assert len(kids) == 1
    assert kids[0].code == "001"
    assert kids[0].name == "Lokalunter"


def test_create_pair_on_tools_host_posts_both_to_weclapp(admin_client, db_session):
    code = _unused_code(db_session)
    mock_wc = MagicMock()
    mock_wc.post.side_effect = [
        {"id": "p1", "name": "Toolshaupt"},
        {"id": "c1", "name": "Toolsunter"},
    ]
    with (
        patch("app.routes.gruppen.weclapp_category_writes_allowed", return_value=True),
        patch("app.routes.gruppen.weclapp_client_for", return_value=mock_wc),
    ):
        response = admin_client.post(
            "/gruppen",
            data={
                "code": code,
                "name": "Toolshaupt",
                "unter_code": "002",
                "unter_name": "Toolsunter",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert mock_wc.post.call_count == 2
    assert mock_wc.post.call_args_list[0].kwargs["json"] == {
        "name": "Toolshaupt",
        "description": code,
    }
    assert mock_wc.post.call_args_list[1].kwargs["json"]["parentCategoryId"] == "p1"
    parent = db_session.scalars(select(Hauptgruppe).where(Hauptgruppe.code == code)).one()
    assert parent.name == "Toolshaupt"


def test_create_untergruppe_on_tools_host_posts_child(admin_client, db_session):
    parent = _make_hauptgruppe(db_session, name="Bestehend")
    db_session.flush()
    mock_wc = MagicMock()
    mock_wc.iter_pages.return_value = [
        {"id": "p1", "name": "Bestehend", "parentCategoryId": None},
    ]
    mock_wc.post.return_value = {"id": "c9"}
    with (
        patch("app.routes.gruppen.weclapp_category_writes_allowed", return_value=True),
        patch("app.routes.gruppen.weclapp_client_for", return_value=mock_wc),
    ):
        response = admin_client.post(
            f"/gruppen/{parent.id}/untergruppen",
            data={"code": "008", "name": "Neueunter"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    mock_wc.post.assert_called_once()
    payload = mock_wc.post.call_args.kwargs["json"]
    assert payload["parentCategoryId"] == "p1"
    assert payload["name"] == "Neueunter"
    assert payload["description"] == "008"


def test_create_pair_weclapp_failure_rolls_back(admin_client, db_session):
    from scripts.weclapp.client import WeclappError

    code = _unused_code(db_session)
    mock_wc = MagicMock()
    mock_wc.post.side_effect = WeclappError("boom", status_code=400)
    with (
        patch("app.routes.gruppen.weclapp_category_writes_allowed", return_value=True),
        patch("app.routes.gruppen.weclapp_client_for", return_value=mock_wc),
    ):
        response = admin_client.post(
            "/gruppen",
            data={
                "code": code,
                "name": "Failhaupt",
                "unter_code": "001",
                "unter_name": "Failunter",
            },
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert "weclapp" in response.text
    found = db_session.scalars(select(Hauptgruppe).where(Hauptgruppe.code == code)).all()
    assert found == []


def test_create_hauptgruppe_with_untergruppe_helper(db_session):
    code = _unused_code(db_session)
    parent, child = create_hauptgruppe_with_untergruppe(
        db_session,
        code=code,
        name="Paarhaupt",
        unter_code="010",
        unter_name="Paarunter",
        actor=ACTOR,
    )
    db_session.flush()
    assert parent.code == code
    assert child.hauptgruppe_id == parent.id
    assert child.code == "010"

