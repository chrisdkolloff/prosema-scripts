"""Dedicated weclapp PUT for admin article renumbering. Not build_article_put."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article_renumber_eligibility import (
    EligibilityResult,
    evaluate_eligibility,
    live_has_supply_source,
)
from app.article_write import ArticleWriteOutcome, ArticleWriteResult, _from_weclapp_error, _unavailable
from app.audit import record_audit_log
from app.models import (
    ArticleSnapshotRow,
    RetiredArticleNumber,
    WeclappArticle,
)
from app.weclapp import map_weclapp_error
from core.article_payload import ARTICLE_NUMBER_FIELD, LABEL_ALIASES
from scripts.weclapp.client import WeclappClient, WeclappError

ENTITY_TYPE = "weclapp_article"
ACTION_RENUMBER = "article_renumbered"


def build_article_number_put(*, version: str, article_number: str) -> dict[str, str]:
    """Narrow payload: version + articleNumber only."""
    return {"version": str(version).strip(), "articleNumber": str(article_number).strip()}


def _set_snapshot_row_number(data: dict[str, Any], new_number: str) -> None:
    keys = {ARTICLE_NUMBER_FIELD, *LABEL_ALIASES.get(ARTICLE_NUMBER_FIELD, ())}
    for key in keys:
        if key in data:
            data[key] = new_number
            return
    data["Prosema Artikelnummer"] = new_number


def _update_local_mirrors(
    db: Session,
    *,
    weclapp_id: str,
    old_number: str,
    new_number: str,
    snapshot_id: Any,
) -> None:
    mirror = db.get(WeclappArticle, weclapp_id)
    if mirror is not None:
        mirror.article_number = new_number
    if snapshot_id is not None:
        row = db.scalars(
            select(ArticleSnapshotRow).where(
                ArticleSnapshotRow.snapshot_id == snapshot_id,
                ArticleSnapshotRow.weclapp_id == weclapp_id,
            )
        ).first()
        if row is None and old_number:
            row = db.scalars(
                select(ArticleSnapshotRow).where(
                    ArticleSnapshotRow.snapshot_id == snapshot_id,
                    ArticleSnapshotRow.article_number == old_number,
                )
            ).first()
        if row is not None:
            row.article_number = new_number
            data = dict(row.data or {})
            _set_snapshot_row_number(data, new_number)
            row.data = data


def update_article_number(
    *,
    db: Session,
    client: WeclappClient,
    article_id: str,
    new_number: str,
    actor_oid: str,
    actor_name: str,
    eligibility: EligibilityResult,
    destination_pair: tuple[str, str],
    shopify_sku_match: bool,
    prefetch_ctx: Any,
    snapshot_id: Any = None,
    transform_run_id: str | None = None,
    transform_chunk_id: str | None = None,
) -> ArticleWriteResult:
    """Live eligibility gate, PUT articleNumber, tombstone, local mirrors, audit."""
    article_id = str(article_id).strip()
    new_number = str(new_number).strip()
    actor_name = actor_name or actor_oid

    try:
        article = client.get(f"/article/id/{article_id}")
    except WeclappError as exc:
        mapped = _from_weclapp_error(article_id, exc)
        if mapped is not None:
            return mapped
        status = exc.status_code
        if status is None or status == 429 or (isinstance(status, int) and status >= 500):
            return _unavailable(article_id, exc)
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REJECTED,
            article_id=article_id,
            message=str(exc),
            weclapp_detail={"reason_code": eligibility.reason_code or "weclapp_get_failed"},
        )

    if not isinstance(article, dict):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.UNAVAILABLE,
            article_id=article_id,
            message="weclapp GET /article did not return an object",
        )

    old_number = str(article.get("articleNumber") or "").strip()
    live_eligibility = evaluate_eligibility(
        article=article, weclapp_id=article_id, ctx=prefetch_ctx
    )
    if not live_eligibility.ok:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REJECTED,
            article_id=article_id,
            article_number=old_number,
            message=live_eligibility.reason_code or "ineligible",
            weclapp_detail={
                "reason_code": live_eligibility.reason_code,
                "eligibility": live_eligibility.checks,
            },
        )

    if live_has_supply_source(article):
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REJECTED,
            article_id=article_id,
            article_number=old_number,
            message="ineligible_supply_source",
            weclapp_detail={
                "reason_code": "ineligible_supply_source",
                "eligibility": live_eligibility.checks,
            },
        )

    version_before = str(article.get("version") or "").strip()
    if not version_before:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.REFUSED,
            article_id=article_id,
            article_number=old_number,
            message="Live article has no version",
        )

    if old_number == new_number:
        return ArticleWriteResult(
            outcome=ArticleWriteOutcome.UNCHANGED,
            article_id=article_id,
            article_number=old_number,
            version_before=version_before,
            version_after=version_before,
        )

    def _put(version: str) -> tuple[ArticleWriteOutcome, dict[str, Any] | None, str | None]:
        try:
            returned = client.put(
                f"/article/id/{article_id}",
                params={"ignoreMissingProperties": "true"},
                json=build_article_number_put(version=version, article_number=new_number),
            )
        except WeclappError as exc:
            mapped = _from_weclapp_error(article_id, exc)
            if mapped is not None:
                return mapped.outcome, exc.detail, None
            if exc.status_code == 409:
                return ArticleWriteOutcome.CONFLICT, exc.detail, None
            if exc.status_code is None or exc.status_code == 429 or (
                isinstance(exc.status_code, int) and exc.status_code >= 500
            ):
                return ArticleWriteOutcome.UNAVAILABLE, exc.detail, None
            return ArticleWriteOutcome.REJECTED, exc.detail, None
        version_after = version_before
        if isinstance(returned, dict) and returned.get("version") is not None:
            version_after = str(returned.get("version"))
        return ArticleWriteOutcome.UPDATED, returned if isinstance(returned, dict) else None, version_after

    outcome, detail, version_after = _put(version_before)
    if outcome is ArticleWriteOutcome.CONFLICT:
        try:
            article = client.get(f"/article/id/{article_id}")
        except WeclappError as exc:
            mapped = map_weclapp_error(exc)
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.CONFLICT,
                article_id=article_id,
                article_number=old_number,
                version_before=version_before,
                message=str(exc),
                weclapp_detail=detail,
            )
        if not isinstance(article, dict):
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.CONFLICT,
                article_id=article_id,
                article_number=old_number,
                version_before=version_before,
                message="409 retry: refetch failed",
                weclapp_detail=detail,
            )
        if live_has_supply_source(article):
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.REJECTED,
                article_id=article_id,
                article_number=old_number,
                message="ineligible_supply_source",
                weclapp_detail={"reason_code": "ineligible_supply_source"},
            )
        retry_version = str(article.get("version") or "").strip()
        if not retry_version:
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.CONFLICT,
                article_id=article_id,
                article_number=old_number,
                version_before=version_before,
                message="409 retry: no version on refetch",
                weclapp_detail=detail,
            )
        outcome, detail, version_after = _put(retry_version)
        if outcome is ArticleWriteOutcome.CONFLICT:
            return ArticleWriteResult(
                outcome=ArticleWriteOutcome.CONFLICT,
                article_id=article_id,
                article_number=old_number,
                version_before=version_before,
                message="409 after retry",
                weclapp_detail=detail,
            )

    if outcome is not ArticleWriteOutcome.UPDATED:
        return ArticleWriteResult(
            outcome=outcome,
            article_id=article_id,
            article_number=old_number,
            version_before=version_before,
            weclapp_detail=detail,
        )

    haupt, unter = destination_pair
    db.add(
        RetiredArticleNumber(
            weclapp_article_id=article_id,
            retired_number=old_number,
            new_number=new_number,
            destination_haupt=haupt,
            destination_unter=unter,
            created_by_oid=actor_oid,
            created_by_name=actor_name,
        )
    )
    _update_local_mirrors(
        db,
        weclapp_id=article_id,
        old_number=old_number,
        new_number=new_number,
        snapshot_id=snapshot_id,
    )
    audit_detail = {
        "weclapp_id": article_id,
        "old_number": old_number,
        "new_number": new_number,
        "destination_pair": f"{haupt}.{unter}",
        "eligibility": live_eligibility.checks,
        "shopify_sku_match": shopify_sku_match,
        "transform_run_id": transform_run_id,
        "transform_chunk_id": transform_chunk_id,
    }
    record_audit_log(
        db,
        actor={"oid": actor_oid, "name": actor_name},
        entity_type=ENTITY_TYPE,
        entity_id=article_id,
        action=ACTION_RENUMBER,
        detail=audit_detail,
    )
    return ArticleWriteResult(
        outcome=ArticleWriteOutcome.UPDATED,
        article_id=article_id,
        article_number=new_number,
        version_before=version_before,
        version_after=version_after or version_before,
        weclapp_detail=audit_detail,
        put_sent=True,
    )
