"""Create weclapp units from article-registration when Einheit is unknown."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batches import (
    EDITABLE_STATUSES,
    MSG_BATCH_LOCKED,
    BatchEditError,
    RowEditResult,
    display_proposed_article_number,
    effective_values,
    load_batch_rows,
    lookups_for_db,
    reopen_approved_batch,
    resolve_row_groups,
    validate_effective,
)
from app.models import ArticleBatch, WeclappUnit
from app.weclapp import (
    NoWeclappToken,
    WeclappLicenceMissing,
    WeclappTokenInvalid,
    map_weclapp_error,
    weclapp_client_for,
)
from app.weclapp_units import catalogue_unit_id, fold_unit_word
from scripts.weclapp.client import WeclappError

MSG_NOT_EDITABLE = MSG_BATCH_LOCKED
MSG_NAME_REQUIRED = "Einheit fehlt"
MSG_NO_UNIT_ID = "weclapp lieferte keine Einheit-ID"


def _find_catalogue_unit(db: Session, name: str) -> WeclappUnit | None:
    units = list(db.scalars(select(WeclappUnit)).all())
    unit_id = catalogue_unit_id(units, name)
    if not unit_id:
        return None
    return db.get(WeclappUnit, unit_id)


def _upsert_unit_row(
    db: Session,
    *,
    weclapp_id: str,
    name: str,
    description: str,
) -> WeclappUnit:
    now = datetime.now(UTC)
    row = db.get(WeclappUnit, weclapp_id)
    if row is None:
        row = WeclappUnit(
            weclapp_id=weclapp_id,
            name=name,
            description=description,
            last_seen_at=now,
        )
        db.add(row)
    else:
        row.name = name
        row.description = description
        row.last_seen_at = now
    db.flush()
    return row


def _revalidate_matching_rows(
    db: Session, batch: ArticleBatch, name: str
) -> list[RowEditResult]:
    lookups = lookups_for_db(db)
    key = fold_unit_word(name)
    results: list[RowEditResult] = []
    for row in load_batch_rows(db, batch.id):
        values = effective_values(row)
        if fold_unit_word(values.get("Einheit", "")) != key:
            continue
        haupt, unter, group_error = resolve_row_groups(db, values)
        row.resolved_hauptgruppe_id = haupt.id if haupt is not None else None
        row.resolved_untergruppe_id = unter.id if unter is not None else None
        row.validation_error = validate_effective(
            values, group_error, lookups=lookups
        )
        results.append(
            RowEditResult(
                id=row.id,
                proposed_article_number=display_proposed_article_number(row),
                validation_error=row.validation_error or "",
                include=bool(row.include),
            )
        )
    return results


def create_unit_for_batch(
    db: Session,
    batch: ArticleBatch,
    *,
    name: str,
    actor_oid: str,
) -> tuple[WeclappUnit, list[RowEditResult], bool]:
    """Create or reuse a weclapp unit, then revalidate matching batch rows.

    Returns ``(unit, row_results, created)`` where ``created`` is True only when
    ``POST /unit`` ran.
    """
    if batch.status not in EDITABLE_STATUSES:
        raise BatchEditError(MSG_NOT_EDITABLE, status_code=409)
    reopen_approved_batch(db, batch)
    text = (name or "").strip()
    if not text:
        raise BatchEditError(MSG_NAME_REQUIRED, field="Einheit")

    existing = _find_catalogue_unit(db, text)
    if existing is not None:
        results = _revalidate_matching_rows(db, batch, text)
        return existing, results, False

    try:
        client = weclapp_client_for(db, actor_oid)
        response = client.post("/unit", json={"name": text, "description": text})
    except NoWeclappToken as exc:
        raise BatchEditError(
            "Kein weclapp-Token hinterlegt. Bitte unter Einstellungen verbinden.",
            status_code=400,
        ) from exc
    except WeclappError as exc:
        mapped = map_weclapp_error(exc)
        if isinstance(mapped, (WeclappTokenInvalid, WeclappLicenceMissing)):
            raise BatchEditError(str(mapped), status_code=400) from exc
        detail = str(exc).strip()
        raise BatchEditError(
            detail or f"weclapp API Fehler {exc.status_code or ''}".strip(),
            status_code=400,
        ) from exc

    unit_id = str((response or {}).get("id") or "").strip()
    if not unit_id:
        raise BatchEditError(MSG_NO_UNIT_ID, status_code=502)

    unit_name = str((response or {}).get("name") or text).strip() or text
    description = str((response or {}).get("description") or text).strip() or text
    unit = _upsert_unit_row(
        db, weclapp_id=unit_id, name=unit_name, description=description
    )
    results = _revalidate_matching_rows(db, batch, text)
    return unit, results, True


def row_results_payload(results: list[RowEditResult]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item.id),
            "proposed_article_number": item.proposed_article_number,
            "validation_error": item.validation_error,
            "include": item.include,
            "corrected": item.corrected,
            "number_reassigned": item.number_reassigned,
            "message": "",
        }
        for item in results
    ]
