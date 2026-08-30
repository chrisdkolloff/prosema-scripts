"""Per-user weclapp credentials: encrypt, load, and map access failures.

``weclapp_client_for`` is the only constructor for a weclapp client in the
web app. Decrypt happens only here. Plaintext must not appear in a session,
template context, log line, or exception message.

weclapp documents 401 as a wrong/missing AuthenticationToken and 403 as
authenticated but lacking privileges for the operation
(https://www.weclapp.com/api/). A token whose user has a role but no
licence is therefore distinguishable from an invalid token: 403 vs 401.
Empty result sets are not used as a licence signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings
from app.models import UserWeclappToken
from scripts.weclapp.client import WeclappClient, WeclappError
from scripts.weclapp.config import WeclappConfig

ZURICH = ZoneInfo("Europe/Zurich")

MSG_NO_TOKEN = "Kein weclapp-Token hinterlegt."
MSG_INVALID = "weclapp-Token ungültig."
MSG_NO_LICENCE = (
    "Keine weclapp-Lizenz zugewiesen. Aktuell hat vermutlich jemand anderes die Lizenz."
)
MSG_UNREADABLE = "weclapp-Token konnte nicht gelesen werden. Bitte Token neu hinterlegen."
LANDING_NO_TOKEN = "Kein Token hinterlegt"
LANDING_OK = "Zugriff aktiv"
LANDING_NO_LICENCE = "Kein Zugriff — vermutlich keine Lizenz zugewiesen"

SETTINGS_PATH = "/einstellungen"
WECLAPP_TOKEN_PATH = "/einstellungen/weclapp"

LANDING_TOOLS: tuple[dict[str, object], ...] = (
    {
        "name": "Gruppenverwaltung",
        "href": "/gruppen",
        "description": "Haupt- und Untergruppen anlegen, umbenennen und deaktivieren.",
        "needs_weclapp": False,
        "refresh_needs_weclapp": False,
    },
    {
        "name": "Gruppendiagramm",
        "href": "/gruppen/diagramm",
        "description": "Alle Haupt- und Untergruppen als Diagramm anzeigen.",
        "needs_weclapp": False,
        "refresh_needs_weclapp": False,
    },
    {
        "name": "Artikelregistrierung",
        "href": "/artikel-registrierung",
        "description": "Neue Artikel per Excel oder manuell erfassen, prüfen und an weclapp senden.",
        "needs_weclapp": True,
        "refresh_needs_weclapp": False,
    },
    {
        "name": "Artikelübersicht",
        "href": "/artikel-uebersicht",
        "description": "Aktueller Stand aller Artikel aus weclapp, nur zum Lesen.",
        "needs_weclapp": False,
        "refresh_needs_weclapp": True,
    },
    {
        "name": "Bezugsquellenexport",
        "href": "/bezugsquellen",
        "description": "CSV-Datei für den Bezugsquellen-Import in weclapp erzeugen.",
        "needs_weclapp": False,
        "refresh_needs_weclapp": True,
    },
    {
        "name": "Buchhaltungsexport",
        "href": "/buchhaltung-export",
        "description": "Daten für die Treuhandstelle aufbereiten und exportieren.",
        "needs_weclapp": True,
        "refresh_needs_weclapp": False,
    },
)


class NoWeclappToken(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_NO_TOKEN)


class WeclappTokenInvalid(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_INVALID)


class WeclappLicenceMissing(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_NO_LICENCE)


class WeclappTokenUnreadable(Exception):
    def __init__(self) -> None:
        super().__init__(MSG_UNREADABLE)


@dataclass(frozen=True)
class WeclappTokenMeta:
    stored: bool
    created_at: datetime | None
    last_verified_at: datetime | None
    last_verified_ok: bool | None


@dataclass(frozen=True)
class WeclappAccess:
    kind: str
    message: str
    stored_at: datetime | None = None
    last_verified_at: datetime | None = None


def format_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ZURICH).strftime("%d.%m.%Y, %H:%M")


def _fernet(key: str | bytes | None = None) -> Fernet:
    raw = key if key is not None else settings.token_encryption_key
    if isinstance(raw, str):
        raw = raw.encode("ascii")
    return Fernet(raw)


def encrypt_token(plaintext: str, key: str | bytes | None = None) -> bytes:
    return _fernet(key).encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes, key: str | bytes | None = None) -> str:
    return _fernet(key).decrypt(ciphertext).decode("utf-8")


def get_token_meta(db: Session, oid: str) -> WeclappTokenMeta:
    row = db.get(UserWeclappToken, oid)
    if row is None:
        return WeclappTokenMeta(
            stored=False,
            created_at=None,
            last_verified_at=None,
            last_verified_ok=None,
        )
    return WeclappTokenMeta(
        stored=True,
        created_at=row.created_at,
        last_verified_at=row.last_verified_at,
        last_verified_ok=row.last_verified_ok,
    )


def store_token(db: Session, oid: str, plaintext: str) -> None:
    token = plaintext.strip()
    if not token:
        raise ValueError("Token darf nicht leer sein.")
    now = datetime.now(UTC)
    ciphertext = encrypt_token(token)
    row = db.get(UserWeclappToken, oid)
    if row is None:
        db.add(
            UserWeclappToken(
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


def delete_token(db: Session, oid: str) -> None:
    row = db.get(UserWeclappToken, oid)
    if row is not None:
        db.delete(row)
        db.commit()


def weclapp_client_for(db: Session, oid: str) -> WeclappClient:
    row = db.get(UserWeclappToken, oid)
    if row is None:
        raise NoWeclappToken()
    try:
        plaintext = decrypt_token(row.token_encrypted)
    except InvalidToken as exc:
        raise WeclappTokenUnreadable() from exc
    tenant = settings.weclapp_tenant.strip()
    if not tenant:
        raise RuntimeError("WECLAPP_TENANT ist nicht konfiguriert.")
    config = WeclappConfig(tenant=tenant, api_token=plaintext)
    return WeclappClient(config)


def map_weclapp_error(exc: WeclappError) -> Exception:
    status = exc.status_code
    error_code = ""
    if isinstance(exc.detail, dict):
        error_code = str(exc.detail.get("error") or "").casefold()
    if status == 401 or error_code == "unauthorized":
        return WeclappTokenInvalid()
    if status == 403 or error_code == "forbidden":
        return WeclappLicenceMissing()
    return exc


def _set_verified(db: Session, oid: str, *, ok: bool) -> None:
    row = db.get(UserWeclappToken, oid)
    if row is None:
        return
    row.last_verified_ok = ok
    if ok:
        row.last_verified_at = datetime.now(UTC)
    db.commit()


def probe_weclapp(db: Session, oid: str) -> None:
    """One cheap authenticated read. Updates last_verified_* on 200/401/403."""
    client = weclapp_client_for(db, oid)
    try:
        client.get("/currency", params={"pageSize": 1})
    except WeclappError as exc:
        mapped = map_weclapp_error(exc)
        if isinstance(mapped, (WeclappTokenInvalid, WeclappLicenceMissing)):
            _set_verified(db, oid, ok=False)
            raise mapped from exc
        raise
    _set_verified(db, oid, ok=True)


def check_weclapp_access(db: Session, oid: str) -> WeclappAccess:
    try:
        probe_weclapp(db, oid)
    except NoWeclappToken:
        return WeclappAccess(kind="missing", message=LANDING_NO_TOKEN)
    except WeclappTokenInvalid:
        meta = get_token_meta(db, oid)
        return WeclappAccess(
            kind="invalid",
            message=MSG_INVALID,
            stored_at=meta.created_at,
            last_verified_at=meta.last_verified_at,
        )
    except WeclappLicenceMissing:
        meta = get_token_meta(db, oid)
        return WeclappAccess(
            kind="unlicensed",
            message=LANDING_NO_LICENCE,
            stored_at=meta.created_at,
            last_verified_at=meta.last_verified_at,
        )
    except WeclappTokenUnreadable:
        meta = get_token_meta(db, oid)
        return WeclappAccess(
            kind="unreadable",
            message=MSG_UNREADABLE,
            stored_at=meta.created_at,
            last_verified_at=meta.last_verified_at,
        )
    except WeclappError as exc:
        meta = get_token_meta(db, oid)
        status = f" ({exc.status_code})" if exc.status_code else ""
        return WeclappAccess(
            kind="unreachable",
            message=f"weclapp ist derzeit nicht erreichbar{status}.",
            stored_at=meta.created_at,
            last_verified_at=meta.last_verified_at,
        )
    meta = get_token_meta(db, oid)
    return WeclappAccess(
        kind="ok",
        message=LANDING_OK,
        stored_at=meta.created_at,
        last_verified_at=meta.last_verified_at,
    )


def job_error_message(exc: BaseException) -> str | None:
    """German job.error for token/licence failures; None means use a traceback."""
    if isinstance(
        exc,
        (NoWeclappToken, WeclappTokenInvalid, WeclappLicenceMissing, WeclappTokenUnreadable),
    ):
        return str(exc)
    if isinstance(exc, WeclappError):
        mapped = map_weclapp_error(exc)
        if mapped is not exc:
            return str(mapped)
        if exc.status_code:
            return f"weclapp API Fehler {exc.status_code}"
        return "weclapp API Fehler"
    return None


def public_job_error(error: str | None) -> str | None:
    if not error or error.startswith("Traceback"):
        return None
    return error


def landing_tool_states(access: WeclappAccess) -> list[dict[str, object]]:
    weclapp_ok = access.kind == "ok"
    rows: list[dict[str, object]] = []
    for tool in LANDING_TOOLS:
        depends = bool(tool["needs_weclapp"]) or bool(tool["refresh_needs_weclapp"])
        if depends:
            mark = "Verfügbar" if weclapp_ok else "Aktualisieren nicht möglich"
        else:
            mark = "Verfügbar"
        rows.append({**tool, "mark": mark, "weclapp_ok": weclapp_ok})
    return rows
