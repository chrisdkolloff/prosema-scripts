"""Tests for Entra group-object-ID to application-role mapping."""

from __future__ import annotations

from app.auth import roles_from_group_ids

USERS_ID = "11111111-1111-1111-1111-111111111111"
ADMINS_ID = "22222222-2222-2222-2222-222222222222"


def _roles(groups):
    return roles_from_group_ids(
        groups,
        users_group_id=USERS_ID,
        admins_group_id=ADMINS_ID,
    )


def test_roles_users_only():
    assert _roles([USERS_ID]) == ["user"]


def test_roles_admins_only():
    assert _roles([ADMINS_ID]) == ["admin"]


def test_roles_both():
    assert _roles([USERS_ID, ADMINS_ID]) == ["user", "admin"]


def test_roles_neither():
    assert _roles(["33333333-3333-3333-3333-333333333333"]) == []


def test_roles_claim_absent():
    assert _roles(None) is None
