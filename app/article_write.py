"""Single-article weclapp update. One article, one GET then one PUT.

Uses ``core.article_write_fields`` for the allowlist, payload builder, and
live definition-id resolver. Does not import ``row_to_payload``.

Nothing here is a bulk engine, a route, or an assistant tool.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.weclapp import (
    WeclappLicenceMissing,
    WeclappTokenInvalid,
    map_weclapp_error,
)
from core.article_write_fields import (
    CustomAttributeResolver,
    Location,
    Writability,
    build_article_put,
    write_field,
)
from scripts.weclapp.client import WeclappClient, WeclappError

logger = logging.getLogger(__name__)

GUARD_PREFIX = "999.999"
ENTITY_TYPE = "weclapp_article"
MSG_WRITE_UNKNOWN = (
    "Schreiben in weclapp ausgeführt, Protokoll unvollständig. "
    "Bitte prüfen, nicht erneut anwenden."
)
MSG_AUDIT_RECONSTRUCTED = (
    "Protokoll nachträglich wiederhergestellt, nicht beim Schreiben erfasst."
)


class ArticleWriteOutcome(str, Enum):
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    REFUSED = "REFUSED"
    AUTH = "AUTH"
    GONE = "GONE"
    UNKNOWN = "UNKNOWN"


class ArticleWriteFieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_key: str
    target: str
    location: str
    attribute_definition_id: str | None
    old: str
    new: str


class ArticleWriteAuditDetail(BaseModel):
    """JSONB payload stored on audit_log.detail for article writes."""

    model_config = ConfigDict(extra="forbid")

    weclapp_id: str
    article_number: str
    version_before: str
    version_after: str | None = None
    fields: list[ArticleWriteFieldChange] = Field(default_factory=list)
    transform_run_id: str | None = None
    transform_chunk_id: str | None = None
    reconstructed: bool = False
    reconstructed_note: str | None = None


@dataclass
class ArticleWriteResult:
    outcome: ArticleWriteOutcome
    article_id: str
    article_number: str | None = None
    version_before: str | None = None
    version_after: str | None = None
    message: str | None = None
    weclapp_detail: Any = None
    audit: ArticleWriteAuditDetail | None = None
    put_sent: bool = False
    fields: list[ArticleWriteFieldChange] = field(default_factory=list)


def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def live_field_value(
    article: Mapping[str, Any],
    snapshot_key: str,
    resolver: CustomAttributeResolver,
) -> str:
    """Current weclapp value for a catalogue key, verbatim (including HTML)."""
    spec = write_field(snapshot_key)
    if spec.location is Location.NATIVE:
        return _stringify(article.get(spec.target))
    attr_id = resolver.id_for_label(spec.target)
    for entry in article.get("customAttributes") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("attributeDefinitionId") or "") != attr_id:
            continue
        if "stringValue" in entry and entry["stringValue"] is not None:
            return str(entry["stringValue"])
        return _stringify(entry.get("stringValue"))
    return ""


def _attr_id(spec, resolver: CustomAttributeResolver) -> str | None:
    if spec.location is Location.CUSTOM_ATTR:
        return resolver.id_for_label(spec.target)
    return None


def _validate_requested_keys(changes: Mapping[str, str]) -> ArticleWriteResult | None:
    for snapshot_key in changes:
        try:
            spec = write_field(snapshot_key)
        except KeyError as exc:
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.REFUSED,
                article_id="",
                message=str(exc),
            )
        if spec.writability is not Writability.PASS_1:
            reason = spec.blocker or spec.writability.value
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.REFUSED,
                article_id="",
                message=(
                    f"Cannot write {spec.snapshot_key!r} "
                    f"({spec.writability.value}): {reason}"
                ),
            )
    return None


def _unavailable(article_id: str, exc: WeclappError) -> ArticleWriteResult:
    return ArticleWriteResult(
        outcome=ArticleWriteOutcome.UNAVAILABLE,
        article_id=article_id,
        message=str(exc),
        weclapp_detail=exc.detail,
    )


def _from_weclapp_error(article_id: str, exc: WeclappError) -> ArticleWriteResult | None:
    """Map licence/token and 404; None means the caller should keep classifying."""
    mapped = map_weclapp_error(exc)
    if isinstance(mapped, WeclappTokenInvalid):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.AUTH,
            article_id=article_id,
            message=str(mapped),
            weclapp_detail=exc.detail,
        )
    if isinstance(mapped, WeclappLicenceMissing):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.AUTH,
            article_id=article_id,
            message=str(mapped),
            weclapp_detail=exc.detail,
        )
    if exc.status_code == 404:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.GONE,
            article_id=article_id,
            message=str(exc),
            weclapp_detail=exc.detail,
        )
    return None


def _audit_and_result(
    db: Session,
    *,
    outcome: ArticleWriteOutcome,
    action: str,
    actor_oid: str,
    actor_name: str,
    article_id: str,
    article_number: str,
    version_before: str,
    version_after: str | None,
    fields: list[ArticleWriteFieldChange],
    message: str | None = None,
    weclapp_detail: Any = None,
    put_sent: bool = False,
    transform_run_id: str | None = None,
    transform_chunk_id: str | None = None,
    reconstructed: bool = False,
    reconstructed_note: str | None = None,
) -> ArticleWriteResult:
    detail = ArticleWriteAuditDetail(
        weclapp_id=article_id,
        article_number=article_number,
        version_before=version_before,
        version_after=version_after,
        fields=fields,
        transform_run_id=transform_run_id,
        transform_chunk_id=transform_chunk_id,
        reconstructed=reconstructed,
        reconstructed_note=reconstructed_note,
    )
    record_audit_log(
        db,
        actor={"oid": actor_oid, "name": actor_name},
        entity_type=ENTITY_TYPE,
        entity_id=article_id,
        action=action,
        detail=detail.model_dump(mode="json"),
    )
    return ArticleWriteResult(
        outcome=outcome,
        article_id=article_id,
        article_number=article_number,
        version_before=version_before,
        version_after=version_after,
        message=message,
        weclapp_detail=weclapp_detail,
        audit=detail,
        put_sent=put_sent,
        fields=fields,
    )


def _unknown_after_put(
    article_id: str,
    *,
    article_number: str,
    version_before: str,
    version_after: str | None,
    fields: list[ArticleWriteFieldChange],
    weclapp_detail: Any = None,
) -> ArticleWriteResult:
    return ArticleWriteResult(
        outcome=ArticleWriteOutcome.UNKNOWN,
        article_id=article_id,
        article_number=article_number,
        version_before=version_before,
        version_after=version_after,
        message=MSG_WRITE_UNKNOWN,
        weclapp_detail=weclapp_detail,
        put_sent=True,
        fields=fields,
    )


def _audit_after_put(**kwargs: Any) -> ArticleWriteResult:
    """Audit after a weclapp PUT. Failure must not look like 'never attempted'."""
    try:
        return _audit_and_result(**kwargs)
    except Exception:
        logger.exception(
            "audit_log write failed after weclapp PUT article_id=%s",
            kwargs.get("article_id"),
        )
        return _unknown_after_put(
            str(kwargs.get("article_id") or ""),
            article_number=str(kwargs.get("article_number") or ""),
            version_before=str(kwargs.get("version_before") or ""),
            version_after=kwargs.get("version_after"),
            fields=list(kwargs.get("fields") or []),
            weclapp_detail=kwargs.get("weclapp_detail"),
        )


def update_article(
    *,
    db: Session,
    client: WeclappClient,
    resolver: CustomAttributeResolver,
    article_id: str,
    changes: Mapping[str, str],
    actor_oid: str,
    actor_name: str | None = None,
    allow_live: bool = False,
    expected_version: str | None = None,
    transform_run_id: str | None = None,
    transform_chunk_id: str | None = None,
) -> ArticleWriteResult:
    """GET one article, PUT only keys whose live value differs.

    ``allow_live`` lifts the 999.999 article-number guard. Later prompts pass
    it deliberately; this caller should not.

    ``expected_version`` is sent on the PUT when given (preview's
    ``version_at_preview``). A stale value yields 409 rather than last-write-wins
    against the live GET version. The live GET still drives the field diff.
    """
    actor_name = actor_name or actor_oid
    article_id = str(article_id).strip()
    refused = _validate_requested_keys(changes)
    if refused is not None:
        refused.article_id = article_id
        return refused

    try:
        resolver.load()
    except (ValueError, WeclappError) as exc:
        if isinstance(exc, WeclappError):
            mapped = _from_weclapp_error(article_id, exc)
            if mapped is not None:
                return mapped
            status = exc.status_code
            if status is None or status == 429 or (status >= 500):
                return _unavailable(article_id, exc)
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.REFUSED,
                article_id=article_id,
                message=str(exc),
                weclapp_detail=exc.detail,
            )
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            message=str(exc),
        )

    try:
        article = client.get(f"/article/id/{article_id}")
    except WeclappError as exc:
        mapped = _from_weclapp_error(article_id, exc)
        if mapped is not None:
            return mapped
        status = exc.status_code
        if status == 409:
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.CONFLICT,
                article_id=article_id,
                message=str(exc),
                weclapp_detail=exc.detail,
            )
        if status is None or status == 429 or (isinstance(status, int) and status >= 500):
            return _unavailable(article_id, exc)
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REJECTED,
            article_id=article_id,
            message=str(exc),
            weclapp_detail=exc.detail,
        )

    if not isinstance(article, dict):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.UNAVAILABLE,
            article_id=article_id,
            message="weclapp GET /article did not return an object",
        )

    article_number = _stringify(article.get("articleNumber"))
    version_before = _stringify(article.get("version"))
    if not version_before:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            message="Live article has no version; refusing to PUT without one",
        )

    if not allow_live and not article_number.startswith(GUARD_PREFIX):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            message=(
                f"Refusing article {article_number!r}: number does not start "
                f"with {GUARD_PREFIX}. Pass allow_live=True to lift this guard."
            ),
        )

    try:
        diffs: list[ArticleWriteFieldChange] = []
        payload_changes: dict[str, str] = {}
        for snapshot_key, new_value in changes.items():
            spec = write_field(snapshot_key)
            old = live_field_value(article, snapshot_key, resolver)
            new = "" if new_value is None else str(new_value)
            if old == new:
                continue
            diffs.append(
                ArticleWriteFieldChange(
                    snapshot_key=snapshot_key,
                    target=spec.target,
                    location=spec.location.value,
                    attribute_definition_id=_attr_id(spec, resolver),
                    old=old,
                    new=new,
                )
            )
            payload_changes[snapshot_key] = new
    except (ValueError, KeyError) as exc:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            message=str(exc),
        )

    if not payload_changes:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.UNCHANGED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            version_after=version_before,
        )

    put_version = (
        str(expected_version).strip() if expected_version is not None else version_before
    )
    if expected_version is not None and not put_version:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            message="expected_version is empty; refusing to PUT without a version",
        )

    try:
        body, params = build_article_put(
            article_id, put_version, resolver, payload_changes
        )
    except (ValueError, KeyError) as exc:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            message=str(exc),
            fields=diffs,
        )

    try:
        returned = client.put(
            f"/article/id/{article_id}",
            params=params,
            json=body,
        )
    except WeclappError as exc:
        mapped = _from_weclapp_error(article_id, exc)
        if mapped is not None:
            return mapped
        status = exc.status_code
        if status == 409:
            return _audit_after_put(
                db=db,
                outcome=ArticleWriteOutcome.CONFLICT,
                action="conflict",
                actor_oid=actor_oid,
                actor_name=actor_name,
                article_id=article_id,
                article_number=article_number,
                version_before=version_before,
                version_after=None,
                fields=diffs,
                message=str(exc),
                weclapp_detail=exc.detail,
                put_sent=True,
                transform_run_id=transform_run_id,
                transform_chunk_id=transform_chunk_id,
            )
        if status == 400:
            return _audit_after_put(
                db=db,
                outcome=ArticleWriteOutcome.REJECTED,
                action="rejected",
                actor_oid=actor_oid,
                actor_name=actor_name,
                article_id=article_id,
                article_number=article_number,
                version_before=version_before,
                version_after=None,
                fields=diffs,
                message=str(exc),
                weclapp_detail=exc.detail,
                put_sent=True,
                transform_run_id=transform_run_id,
                transform_chunk_id=transform_chunk_id,
            )
        return _unavailable(article_id, exc)

    version_after = version_before
    if isinstance(returned, dict) and returned.get("version") is not None:
        version_after = _stringify(returned.get("version"))

    return _audit_after_put(
        db=db,
        outcome=ArticleWriteOutcome.UPDATED,
        action="updated",
        actor_oid=actor_oid,
        actor_name=actor_name,
        article_id=article_id,
        article_number=article_number,
        version_before=version_before,
        version_after=version_after,
        fields=diffs,
        put_sent=True,
        transform_run_id=transform_run_id,
        transform_chunk_id=transform_chunk_id,
    )


CATEGORY_SNAPSHOT_KEY = "weclapp Kategorie-ID"


def update_article_category(
    *,
    db: Session,
    client: WeclappClient,
    article_id: str,
    category_id: str,
    actor_oid: str,
    actor_name: str | None = None,
    allow_live: bool = False,
    expected_version: str | None = None,
    transform_run_id: str | None = None,
    transform_chunk_id: str | None = None,
) -> ArticleWriteResult:
    """PUT only ``articleCategoryId``. Not the shop LIST Hauptgruppe/Untergruppe."""
    actor_name = actor_name or actor_oid
    article_id = str(article_id).strip()
    new_category = str(category_id or "").strip()
    if not new_category:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            message="Ziel-Kategorie fehlt",
        )

    try:
        article = client.get(f"/article/id/{article_id}")
    except WeclappError as exc:
        mapped = _from_weclapp_error(article_id, exc)
        if mapped is not None:
            return mapped
        status = exc.status_code
        if status == 409:
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.CONFLICT,
                article_id=article_id,
                message=str(exc),
                weclapp_detail=exc.detail,
            )
        if status is None or status == 429 or (isinstance(status, int) and status >= 500):
            return _unavailable(article_id, exc)
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REJECTED,
            article_id=article_id,
            message=str(exc),
            weclapp_detail=exc.detail,
        )

    if not isinstance(article, dict):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.UNAVAILABLE,
            article_id=article_id,
            message="weclapp GET /article did not return an object",
        )

    article_number = _stringify(article.get("articleNumber"))
    version_before = _stringify(article.get("version"))
    if not version_before:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            message="Live article has no version; refusing to PUT without one",
        )

    if not allow_live and not article_number.startswith(GUARD_PREFIX):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            message=(
                f"Refusing article {article_number!r}: number does not start "
                f"with {GUARD_PREFIX}. Pass allow_live=True to lift this guard."
            ),
        )

    old_category = _stringify(article.get("articleCategoryId"))
    if old_category == new_category:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.UNCHANGED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            version_after=version_before,
        )

    diffs = [
        ArticleWriteFieldChange(
            snapshot_key=CATEGORY_SNAPSHOT_KEY,
            target="articleCategoryId",
            location=Location.NATIVE.value,
            attribute_definition_id=None,
            old=old_category,
            new=new_category,
        )
    ]
    put_version = (
        str(expected_version).strip() if expected_version is not None else version_before
    )
    if expected_version is not None and not put_version:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=article_number,
            version_before=version_before,
            message="expected_version is empty; refusing to PUT without a version",
        )

    try:
        returned = client.put(
            f"/article/id/{article_id}",
            params={"ignoreMissingProperties": "true"},
            json={"version": put_version, "articleCategoryId": new_category},
        )
    except WeclappError as exc:
        mapped = _from_weclapp_error(article_id, exc)
        if mapped is not None:
            return mapped
        status = exc.status_code
        if status == 409:
            return _audit_after_put(
                db=db,
                outcome=ArticleWriteOutcome.CONFLICT,
                action="conflict",
                actor_oid=actor_oid,
                actor_name=actor_name,
                article_id=article_id,
                article_number=article_number,
                version_before=version_before,
                version_after=None,
                fields=diffs,
                message=str(exc),
                weclapp_detail=exc.detail,
                put_sent=True,
                transform_run_id=transform_run_id,
                transform_chunk_id=transform_chunk_id,
            )
        if status == 400:
            return _audit_after_put(
                db=db,
                outcome=ArticleWriteOutcome.REJECTED,
                action="rejected",
                actor_oid=actor_oid,
                actor_name=actor_name,
                article_id=article_id,
                article_number=article_number,
                version_before=version_before,
                version_after=None,
                fields=diffs,
                message=str(exc),
                weclapp_detail=exc.detail,
                put_sent=True,
                transform_run_id=transform_run_id,
                transform_chunk_id=transform_chunk_id,
            )
        return _unavailable(article_id, exc)

    version_after = version_before
    if isinstance(returned, dict) and returned.get("version") is not None:
        version_after = _stringify(returned.get("version"))

    return _audit_after_put(
        db=db,
        outcome=ArticleWriteOutcome.UPDATED,
        action="updated",
        actor_oid=actor_oid,
        actor_name=actor_name,
        article_id=article_id,
        article_number=article_number,
        version_before=version_before,
        version_after=version_after,
        fields=diffs,
        put_sent=True,
        transform_run_id=transform_run_id,
        transform_chunk_id=transform_chunk_id,
    )
