"""Delegated Microsoft Graph tokens (SharePoint folder access for signed-in users)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.config import settings
from app.models import UserGraphToken
from app.weclapp import decrypt_token, encrypt_token

GRAPH_DELEGATED_SCOPES = (
    "openid profile email offline_access "
    "https://graph.microsoft.com/Files.Read.All"
)
MSG_NO_GRAPH_TOKEN = (
    "Kein Microsoft-Zugriff für SharePoint hinterlegt. "
    "Bitte abmelden und erneut anmelden — beim Login muss PROSEMA "
    "Dateien in SharePoint lesen dürfen."
)
MSG_GRAPH_UNREADABLE = (
    "Microsoft-Zugriff konnte nicht gelesen werden. "
    "Bitte abmelden, erneut anmelden und den Zugriff bestätigen."
)


class NoGraphToken(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_NO_GRAPH_TOKEN)


class GraphTokenUnreadable(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_GRAPH_UNREADABLE)


def store_graph_refresh_token(db: Session, oid: str, refresh_token: str) -> None:
    token = refresh_token.strip()
    if not token:
        return
    now = datetime.now(UTC)
    ciphertext = encrypt_token(token)
    row = db.get(UserGraphToken, oid)
    if row is None:
        db.add(
            UserGraphToken(
                oid=oid,
                refresh_token_encrypted=ciphertext,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        row.refresh_token_encrypted = ciphertext
        row.updated_at = now
    db.commit()


def has_graph_refresh_token(db: Session, oid: str) -> bool:
    return db.get(UserGraphToken, oid) is not None


def _refresh_access_token(refresh_token: str) -> str:
    token_url = (
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    )
    response = httpx.post(
        token_url,
        data={
            "client_id": settings.entra_client_id,
            "client_secret": settings.entra_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": GRAPH_DELEGATED_SCOPES,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise NoGraphToken()
    payload = response.json()
    access = str(payload.get("access_token") or "").strip()
    if not access:
        raise NoGraphToken()
    return access


def get_graph_access_token(db: Session, oid: str) -> str:
    row = db.get(UserGraphToken, oid)
    if row is None:
        raise NoGraphToken()
    try:
        refresh = decrypt_token(row.refresh_token_encrypted)
    except InvalidToken as exc:
        raise GraphTokenUnreadable() from exc
    return _refresh_access_token(refresh)
