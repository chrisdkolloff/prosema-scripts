"""Entra ID OpenID Connect login and session-based authorisation."""

from __future__ import annotations

import base64
import json
from typing import Any, TypedDict

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from app.config import settings

oauth = OAuth()
oauth.register(
    name="entra",
    client_id=settings.entra_client_id,
    client_secret=settings.entra_client_secret,
    server_metadata_url=(
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        "/v2.0/.well-known/openid-configuration"
    ),
    client_kwargs={"scope": "openid profile email"},
)


class SessionUser(TypedDict):
    oid: str
    name: str
    email: str
    roles: list[str]


class GroupsClaimMissing(Exception):
    """Raised when the ID token has no ``groups`` claim at all."""


def roles_from_group_ids(
    groups: list[str] | None,
    *,
    users_group_id: str,
    admins_group_id: str,
) -> list[str] | None:
    """Map Entra group object IDs to application roles.

    Returns ``None`` if the groups claim is absent (token misconfiguration).
    Returns a possibly empty list if the claim is present. Admin membership
    does not imply user membership; both groups must be assigned in Entra.
    """
    if groups is None:
        return None
    present = {str(group_id).casefold() for group_id in groups}
    roles: list[str] = []
    if users_group_id.casefold() in present:
        roles.append("user")
    if admins_group_id.casefold() in present:
        roles.append("admin")
    return roles


def _claims_from_token(token: dict[str, Any]) -> dict[str, Any]:
    """Merge ID-token payload with Authlib userinfo so custom Entra claims remain."""
    claims = dict(token.get("userinfo") or {})
    id_token = token.get("id_token")
    if not isinstance(id_token, str) or id_token.count(".") < 2:
        return claims
    payload = id_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    raw = json.loads(base64.urlsafe_b64decode(payload))
    return {**raw, **claims}


def _normalise_groups(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def session_user_from_claims(claims: dict[str, Any]) -> SessionUser:
    if "groups" not in claims:
        raise GroupsClaimMissing
    roles = roles_from_group_ids(
        _normalise_groups(claims.get("groups")),
        users_group_id=settings.entra_group_users_id,
        admins_group_id=settings.entra_group_admins_id,
    )
    if roles is None:
        raise GroupsClaimMissing
    email = str(claims.get("email") or claims.get("preferred_username") or "")
    name = str(claims.get("name") or claims.get("preferred_username") or email)
    return {
        "oid": str(claims["oid"]),
        "name": name,
        "email": email,
        "roles": roles,
    }


def get_current_user(request: Request) -> SessionUser:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/auth/login"})
    return user


def require_user(user: SessionUser = Depends(get_current_user)) -> SessionUser:
    if "user" not in user.get("roles", []):
        raise HTTPException(status_code=403)
    return user


def require_admin(user: SessionUser = Depends(get_current_user)) -> SessionUser:
    if "admin" not in user.get("roles", []):
        raise HTTPException(status_code=403)
    return user


async def login(request: Request) -> Response:
    return await oauth.entra.authorize_redirect(request, settings.entra_redirect_uri)


async def callback(request: Request) -> Response:
    token = await oauth.entra.authorize_access_token(request)
    claims = _claims_from_token(token)
    try:
        user = session_user_from_claims(claims)
    except GroupsClaimMissing:
        return request.app.state.templates.TemplateResponse(
            request,
            "groups_claim_missing.html",
            {"user": None},
            status_code=500,
        )
    except KeyError:
        raise HTTPException(status_code=400, detail="ID token is missing required claims.")
    request.session.clear()
    request.session["user"] = dict(user)
    return RedirectResponse(url="/", status_code=302)


async def logout(request: Request) -> Response:
    request.session.clear()
    client = oauth.create_client("entra")
    await client.load_server_metadata()
    end_session = client.server_metadata.get("end_session_endpoint")
    if not end_session:
        return RedirectResponse(url="/", status_code=302)
    return RedirectResponse(url=end_session, status_code=302)
