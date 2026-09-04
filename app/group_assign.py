"""Reassign articles to a Hauptgruppe/Untergruppe weclapp category.

Propose-only from Noa. Preview GETs live weclapp; apply PUTs articleCategoryId.
Article numbers are not rewritten.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.groups_service import AmbiguousGroupMatch, CODE_RE, resolve_hauptgruppe, resolve_untergruppe
from app.models import ArticleSnapshot, Hauptgruppe, TransformRow, TransformRun, Untergruppe
from app.transform.live_fetch import fetch_live_articles
from app.transform.schemas import TransformScope
from app.transform.scope import resolve_scope
from app.weclapp import WeclappLicenceMissing, WeclappTokenInvalid, map_weclapp_error, weclapp_client_for
from app.weclapp_categories import (
    category_label,
    find_coded_untergruppe_category,
    list_article_categories,
)
from scripts.weclapp.client import WeclappClient, WeclappError

ZIEL_RE = re.compile(r"^([0-9]{3})\.([0-9]{3})(?:\.[0-9]{4})?$")
CATEGORY_FIELD = "weclapp Kategorie-ID"

MSG_ZIEL = (
    "Zielgruppe muss als Haupt- und Untergruppe angegeben werden, "
    "zum Beispiel 100.130."
)
MSG_HAUPT_MISSING = "Hauptgruppe {code} fehlt in der Gruppenverwaltung."
MSG_UNTER_MISSING = "Untergruppe {pair} fehlt in der Gruppenverwaltung."
MSG_AMBIGUOUS = "Die Angabe «{needle}» ist nicht eindeutig."
MSG_EMPTY_SCOPE = (
    "Bitte den Umfang einschränken. Die ganze Übersicht einer Gruppe "
    "zuzuordnen ist nicht erlaubt."
)
MSG_WECLAPP_MISSING = (
    "Untergruppe {pair} «{name}» fehlt in weclapp. "
    "Bitte zuerst in der Gruppenverwaltung nachziehen."
)
MSG_NUMBERS_UNCHANGED = (
    "Die Artikelnummern bleiben unverändert; geändert wird nur die "
    "weclapp-Kategorie (nicht die Shopify-Auswahllisten)."
)


class GroupAssignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["group_assign"] = "group_assign"
    scope: TransformScope
    hauptgruppe_code: str
    untergruppe_code: str
    hauptgruppe_name: str
    untergruppe_name: str

    @field_validator("hauptgruppe_code", "untergruppe_code")
    @classmethod
    def three_digits(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not CODE_RE.fullmatch(cleaned):
            raise ValueError(MSG_ZIEL)
        return cleaned

    @model_validator(mode="after")
    def names_present(self) -> Self:
        if not str(self.hauptgruppe_name).strip() or not str(self.untergruppe_name).strip():
            raise ValueError(MSG_ZIEL)
        return self

    @property
    def pair(self) -> str:
        return f"{self.hauptgruppe_code}.{self.untergruppe_code}"


def parse_ziel_gruppe(text: str) -> tuple[str, str]:
    cleaned = str(text or "").strip()
    match = ZIEL_RE.fullmatch(cleaned)
    if match is None:
        raise ValueError(MSG_ZIEL)
    return match.group(1), match.group(2)


def resolve_target_group(session: Session, ziel: str) -> tuple[Hauptgruppe, Untergruppe]:
    haupt_code, unter_code = parse_ziel_gruppe(ziel)
    try:
        haupt = resolve_hauptgruppe(session, haupt_code)
    except AmbiguousGroupMatch as exc:
        raise ValueError(MSG_AMBIGUOUS.format(needle=haupt_code)) from exc
    if haupt is None:
        raise ValueError(MSG_HAUPT_MISSING.format(code=haupt_code))
    try:
        unter = resolve_untergruppe(session, haupt, unter_code)
    except AmbiguousGroupMatch as exc:
        raise ValueError(MSG_AMBIGUOUS.format(needle=f"{haupt_code}.{unter_code}")) from exc
    if unter is None:
        raise ValueError(
            MSG_UNTER_MISSING.format(pair=f"{haupt_code}.{unter_code}")
        )
    return haupt, unter


def build_group_assign_spec(
    session: Session,
    *,
    filters: dict[str, Any],
    ziel: str,
) -> GroupAssignSpec:
    conditions = (filters or {}).get("conditions") or []
    if not conditions:
        raise ValueError(MSG_EMPTY_SCOPE)
    haupt, unter = resolve_target_group(session, ziel)
    return GroupAssignSpec(
        scope=TransformScope(query_filter=filters),
        hauptgruppe_code=haupt.code,
        untergruppe_code=unter.code,
        hauptgruppe_name=haupt.name,
        untergruppe_name=unter.name,
    )


def format_group_assign_summary_de(spec: GroupAssignSpec, *, total_count: int | None = None) -> str:
    pair = spec.pair
    name = f"{spec.hauptgruppe_name} / {spec.untergruppe_name}"
    count = ""
    if total_count is not None:
        count = f"{total_count} Artikel: "
    return (
        f"{count}weclapp-Kategorie auf {pair} «{name}» setzen. "
        f"{MSG_NUMBERS_UNCHANGED}"
    )


def _auth_from_error(exc: WeclappError):
    from app.transform.preview import TransformAuthAbort

    mapped = map_weclapp_error(exc)
    if isinstance(mapped, (WeclappTokenInvalid, WeclappLicenceMissing)):
        return TransformAuthAbort(str(mapped))
    return None


def _add_gone(
    db: Session,
    run: TransformRun,
    *,
    article_number: str,
    weclapp_id: str,
    field: str,
) -> None:
    db.add(
        TransformRow(
            run_id=run.id,
            article_number=article_number,
            weclapp_id=weclapp_id,
            version_at_preview=None,
            field=field,
            old_value="",
            new_value="",
            operations_fired=[],
            row_status="GONE",
        )
    )


def _existing_article_numbers(db: Session, run_id: Any) -> set[str]:
    return set(
        db.scalars(select(TransformRow.article_number).where(TransformRow.run_id == run_id))
    )


def run_group_assign_preview(
    db: Session,
    run: TransformRun,
    *,
    oid: str,
    client: WeclappClient | None = None,
) -> dict[str, Any]:
    snapshot = db.get(ArticleSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.status != "complete":
        raise ValueError("Snapshot nicht gefunden oder nicht abgeschlossen")
    spec = GroupAssignSpec.model_validate(run.spec)
    candidates = resolve_scope(db, snapshot, spec)
    done = _existing_article_numbers(db, run.id)
    live = [c for c in candidates if c.article_number not in done]
    run.candidate_count = len(live) + len(done)
    if not live:
        run.status = "previewed"
        run.error = None
        run.case_variants = []
        run.word_positions = {}
        db.flush()
        from app.transform.summary import preview_summary

        summary = preview_summary(run, changed_rows=None if done else 0)
        return {
            "candidate_count": len(done),
            "changed_rows": sum(
                1 for row in (run.rows or []) if row.row_status == "CHANGED"
            ),
            "word_positions": run.word_positions,
            "summary": summary,
        }

    wc = client or weclapp_client_for(db, oid)
    try:
        categories = list_article_categories(wc)
    except WeclappError as exc:
        abort = _auth_from_error(exc)
        if abort is not None:
            raise abort from exc
        raise
    target = find_coded_untergruppe_category(
        categories,
        haupt_name=spec.hauptgruppe_name,
        haupt_code=spec.hauptgruppe_code,
        unter_name=spec.untergruppe_name,
        unter_code=spec.untergruppe_code,
    )
    if target is None or not target.get("id"):
        raise ValueError(
            MSG_WECLAPP_MISSING.format(pair=spec.pair, name=spec.untergruppe_name)
        )
    target_id = str(target["id"])
    target_label = category_label(categories, target_id)

    try:
        fetched = fetch_live_articles(wc, live)
    except WeclappError as exc:
        abort = _auth_from_error(exc)
        if abort is not None:
            raise abort from exc
        raise

    changed = 0
    for candidate in live:
        weclapp_id = candidate.weclapp_id
        if not weclapp_id or weclapp_id in fetched.gone_ids:
            _add_gone(
                db,
                run,
                article_number=candidate.article_number,
                weclapp_id=weclapp_id or "",
                field=CATEGORY_FIELD,
            )
            db.commit()
            continue
        article = fetched.articles.get(weclapp_id)
        if article is None or not isinstance(article, dict):
            _add_gone(
                db,
                run,
                article_number=candidate.article_number,
                weclapp_id=weclapp_id,
                field=CATEGORY_FIELD,
            )
            db.commit()
            continue
        version = str(article.get("version") or "")
        number = str(article.get("articleNumber") or candidate.article_number)
        old_id = str(article.get("articleCategoryId") or "")
        old_label = category_label(categories, old_id)
        status = "CHANGED" if old_id != target_id else "UNCHANGED"
        if status == "CHANGED":
            changed += 1
        db.add(
            TransformRow(
                run_id=run.id,
                article_number=number,
                weclapp_id=weclapp_id,
                version_at_preview=version or None,
                field=CATEGORY_FIELD,
                old_value=old_label,
                new_value=target_label,
                operations_fired=[{"old_id": old_id, "new_id": target_id}],
                row_status=status,
            )
        )
        db.commit()

    run.status = "previewed"
    run.error = None
    run.case_variants = []
    run.word_positions = {}
    db.flush()
    from app.transform.summary import preview_summary

    summary = preview_summary(run, changed_rows=changed)
    return {
        "candidate_count": len(live) + len(done),
        "changed_rows": changed,
        "word_positions": run.word_positions,
        "summary": summary,
    }


def is_group_assign_spec(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("kind") == "group_assign"


def target_category_id_from_row(row: TransformRow) -> str:
    for item in row.operations_fired or []:
        if isinstance(item, dict) and item.get("new_id"):
            return str(item["new_id"])
    return ""
