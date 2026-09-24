"""Per-user Shopify Admin API tokens (encrypted), with env fallback for scripts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.models import UserShopifyToken
from app.weclapp import decrypt_token, encrypt_token, format_dt
from scripts.shopify.client import ShopifyClient, ShopifyError
from scripts.shopify.config import ShopifyConfig, load_config

MSG_NO_TOKEN = (
    "Kein Shopify-Schlüssel hinterlegt. Bitte unter Einstellungen den App-Schlüssel "
    "(Neu) speichern."
)
MSG_INVALID = "Shopify-Token ungültig oder ohne Berechtigung."
MSG_UNREADABLE = (
    "Shopify-Token konnte nicht gelesen werden. Bitte Token neu hinterlegen."
)
LANDING_NO_TOKEN = "Kein Token hinterlegt"
LANDING_OK = "Zugriff aktiv"

SHOPIFY_TOKEN_PATH = "/einstellungen/shopify"


class NoShopifyToken(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_NO_TOKEN)


class ShopifyTokenInvalid(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_INVALID)


class ShopifyTokenUnreadable(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_UNREADABLE)


@dataclass(frozen=True)
class ShopifyTokenMeta:
    stored: bool
    created_at: datetime | None
    last_verified_at: datetime | None
    last_verified_ok: bool | None


@dataclass(frozen=True)
class ShopifyAccess:
    kind: str
    message: str
    stored_at: datetime | None = None
    last_verified_at: datetime | None = None


def get_shopify_token_meta(db: Session, oid: str) -> ShopifyTokenMeta:
    row = db.get(UserShopifyToken, oid)
    if row is None:
        return ShopifyTokenMeta(
            stored=False,
            created_at=None,
            last_verified_at=None,
            last_verified_ok=None,
        )
    return ShopifyTokenMeta(
        stored=True,
        created_at=row.created_at,
        last_verified_at=row.last_verified_at,
        last_verified_ok=row.last_verified_ok,
    )


def store_shopify_token(db: Session, oid: str, plaintext: str) -> None:
    token = plaintext.strip()
    if not token:
        raise ValueError("Token darf nicht leer sein.")
    now = datetime.now(UTC)
    ciphertext = encrypt_token(token)
    row = db.get(UserShopifyToken, oid)
    if row is None:
        db.add(
            UserShopifyToken(
                oid=oid,
                token_encrypted=ciphertext,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        row.token_encrypted = ciphertext
        row.updated_at = now
        row.last_verified_at = None
        row.last_verified_ok = None
    db.commit()


def delete_shopify_token(db: Session, oid: str) -> None:
    row = db.get(UserShopifyToken, oid)
    if row is not None:
        db.delete(row)
        db.commit()


def _access_token_for_user(db: Session, oid: str) -> str | None:
    row = db.get(UserShopifyToken, oid)
    if row is None:
        return None
    try:
        return decrypt_token(row.token_encrypted).strip()
    except InvalidToken as exc:
        raise ShopifyTokenUnreadable() from exc


def load_config_for_user(db: Session, oid: str) -> ShopifyConfig:
    """Per-user secret from Postgres overrides env Shopify credentials."""
    user_token = _access_token_for_user(db, oid)
    if user_token:
        if user_token.startswith("shpat_"):
            return load_config(access_token=user_token)
        return load_config(client_secret=user_token, access_token="")
    try:
        return load_config()
    except ValueError as exc:
        raise NoShopifyToken() from exc


def check_shopify_access(db: Session, oid: str) -> ShopifyAccess:
    meta = get_shopify_token_meta(db, oid)
    if not meta.stored:
        return ShopifyAccess(kind="missing", message=LANDING_NO_TOKEN)
    try:
        probe_shopify(db, oid)
    except NoShopifyToken:
        return ShopifyAccess(kind="missing", message=LANDING_NO_TOKEN)
    except ShopifyTokenInvalid:
        return ShopifyAccess(
            kind="invalid",
            message=MSG_INVALID,
            stored_at=meta.created_at,
            last_verified_at=meta.last_verified_at,
        )
    except ShopifyTokenUnreadable:
        return ShopifyAccess(
            kind="unreadable",
            message=MSG_UNREADABLE,
            stored_at=meta.created_at,
            last_verified_at=meta.last_verified_at,
        )
    except ShopifyError as exc:
        status = f" ({exc.status_code})" if exc.status_code else ""
        return ShopifyAccess(
            kind="unreachable",
            message=f"Shopify ist derzeit nicht erreichbar{status}.",
            stored_at=meta.created_at,
            last_verified_at=meta.last_verified_at,
        )
    meta = get_shopify_token_meta(db, oid)
    return ShopifyAccess(
        kind="ok",
        message=LANDING_OK,
        stored_at=meta.created_at,
        last_verified_at=meta.last_verified_at,
    )


def probe_shopify(db: Session, oid: str) -> str:
    """Verify token with a minimal GraphQL call; update verification metadata."""
    config = load_config_for_user(db, oid)
    client = ShopifyClient(config)
    try:
        data = client.graphql("{ shop { name } }")
    except ShopifyError as exc:
        _mark_verified(db, oid, ok=False)
        if exc.status_code in {401, 403}:
            raise ShopifyTokenInvalid() from exc
        raise
    shop = (data.get("shop") or {}).get("name") or ""
    _mark_verified(db, oid, ok=True)
    if shop:
        return f"Shopify-Verbindung erfolgreich ({shop})."
    return "Shopify-Verbindung erfolgreich."


def _mark_verified(db: Session, oid: str, *, ok: bool) -> None:
    row = db.get(UserShopifyToken, oid)
    if row is None:
        return
    now = datetime.now(UTC)
    row.last_verified_at = now
    row.last_verified_ok = ok
    row.updated_at = now
    db.commit()


def shopify_meta_labels(meta: ShopifyTokenMeta) -> dict[str, str | None]:
    return {
        "shopify_created_at_label": format_dt(meta.created_at),
        "shopify_last_verified_label": format_dt(meta.last_verified_at),
    }
