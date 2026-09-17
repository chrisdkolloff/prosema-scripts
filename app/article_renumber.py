"""Admin renumbering after subgroup reassignment (Artikelnummer neu vergeben)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article_renumber_eligibility import (
    REASON_LABELS_DE,
    EligibilityResult,
    RenumberPrefetch,
    destination_pair_for_article,
    evaluate_eligibility,
    prefetch_renumber_context,
)
from app.models import ArticleSnapshot, ArticleSnapshotRow, TransformRow, TransformRun
from app.numbering_high_water import seed_high_water
from app.shopify_skus import load_shopify_sku_set
from app.transform.live_fetch import fetch_live_articles
from app.transform.schemas import TransformScope
from app.transform.scope import resolve_scope
from app.weclapp import WeclappLicenceMissing, WeclappTokenInvalid, map_weclapp_error, weclapp_client_for
from core.article_payload import ARTICLE_NUMBER_FIELD
from core.numbering import Scheme, parse_group_codes
from scripts.weclapp.client import WeclappClient, WeclappError

KIND = "article_renumber"
FIELD = ARTICLE_NUMBER_FIELD

MSG_SHOPIFY_WARNING = (
    "Achtung: {count} Artikel haben eine Shopify-Variante mit SKU gleich der "
    "bisherigen Artikelnummer. PROSEMA ändert die SKU nicht — bitte manuell "
    "in Shopify nachziehen."
)
MSG_SUPPLY_SOURCE_WARNING = (
    "Achtung: {count} Artikel haben eine aktive Bezugsquelle (Lieferant/SAN: "
    "{examples}). Die Umnummerierung ist in weclapp möglich; PROSEMA aktualisiert "
    "die lokalen Bezugsquellen-Spiegel — bitte bestätigen, bevor Sie freigeben."
)
MSG_ACK_REQUIRED = (
    "Bitte die Shopify-Warnung bestätigen, bevor die Umnummerierung freigegeben wird."
)
MSG_SUPPLY_SOURCE_ACK_REQUIRED = (
    "Bitte die Bezugsquellen-Warnung bestätigen, bevor die Umnummerierung "
    "freigegeben wird."
)
MSG_ADMIN_ONLY = "Nur Administratoren dürfen Artikel umnummerieren."


def assert_admin_renumber_actor(user: dict[str, Any]) -> None:
    if "admin" not in (user.get("roles") or []):
        raise ValueError(MSG_ADMIN_ONLY)


def assert_admin_renumber_job(payload: dict[str, Any]) -> None:
    if not payload.get("requires_admin"):
        return
    roles = payload.get("creator_roles") or []
    if "admin" not in roles:
        raise ValueError(MSG_ADMIN_ONLY)


class ArticleRenumberSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["article_renumber"] = "article_renumber"
    scope: TransformScope


def is_article_renumber_spec(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("kind") == KIND


def _supply_warning_examples(
    lines: list[tuple[str, str, str]],
    *,
    limit: int = 3,
) -> str:
    parts: list[str] = []
    for name, _number, san in lines[:limit]:
        label = f"{name} / {san}" if name and name != "—" else san
        parts.append(label)
    extra = len(lines) - limit
    if extra > 0:
        parts.append(f"… +{extra} weitere")
    return "; ".join(parts) if parts else "—"


def supply_source_warning_to_dict(
    lines: tuple[Any, ...],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in lines:
        if hasattr(line, "supplier_name"):
            out.append(
                {
                    "supplier_name": line.supplier_name,
                    "supplier_number": line.supplier_number,
                    "supplier_article_number": line.supplier_article_number,
                }
            )
        elif isinstance(line, dict):
            out.append(dict(line))
    return out


def format_article_renumber_summary_de(
    *,
    eligible: int,
    rejected: int,
    shopify_warnings: int,
    supply_source_warnings: int = 0,
    supply_source_examples: list[tuple[str, str, str]] | None = None,
) -> str:
    lines = [
        "Artikelnummer neu vergeben (weclapp-Nummer an die Kategorie anpassen).",
        f"{eligible} Artikel können umnummeriert werden, {rejected} abgelehnt.",
    ]
    if shopify_warnings:
        lines.append(MSG_SHOPIFY_WARNING.format(count=shopify_warnings))
    if supply_source_warnings:
        examples = _supply_warning_examples(supply_source_examples or [])
        lines.append(
            MSG_SUPPLY_SOURCE_WARNING.format(
                count=supply_source_warnings,
                examples=examples,
            )
        )
    return "\n".join(lines)


def renumber_payload_from_row(row: TransformRow) -> dict[str, Any]:
    return _payload_from_row(row)


def _payload_from_row(row: TransformRow) -> dict[str, Any]:
    for item in row.operations_fired or []:
        if isinstance(item, dict) and item.get("kind") == KIND:
            return item
    return {}


def approved_number_from_row(row: TransformRow) -> str:
    payload = _payload_from_row(row)
    frozen = str(payload.get("approved_number") or payload.get("proposed_number") or "").strip()
    return frozen


def freeze_renumber_rows(
    rows: list[TransformRow],
    *,
    supply_source_warning_acknowledged: bool = False,
) -> None:
    """Freeze proposed numbers into the approval artefact at approve time."""
    for row in rows:
        payload = _payload_from_row(row)
        if not payload:
            continue
        proposed = str(payload.get("proposed_number") or "").strip()
        if not proposed:
            continue
        payload = {**payload, "approved_number": proposed}
        if payload.get("supply_source_warning") and supply_source_warning_acknowledged:
            payload["supply_source_warning_acknowledged"] = True
        row.operations_fired = [payload]


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
) -> None:
    db.add(
        TransformRow(
            run_id=run.id,
            article_number=article_number,
            weclapp_id=weclapp_id,
            version_at_preview=None,
            field=FIELD,
            old_value=article_number,
            new_value="",
            operations_fired=[],
            row_status="GONE",
        )
    )


def _existing_article_numbers(db: Session, run_id: uuid.UUID) -> set[str]:
    return set(
        db.scalars(select(TransformRow.article_number).where(TransformRow.run_id == run_id))
    )


def _allocate_number(
    reserved: dict[tuple[str, str], int],
    destination: tuple[str, str],
    scheme: Scheme,
) -> str | None:
    haupt, unter = destination
    key = (haupt, unter)
    current = reserved.get(key)
    nxt = scheme.start if current is None else current + scheme.step
    if nxt > scheme.max_running:
        return None
    reserved[key] = nxt
    return scheme.format(haupt, unter, nxt)


def run_article_renumber_preview(
    db: Session,
    run: TransformRun,
    *,
    oid: str,
    client: WeclappClient | None = None,
) -> dict[str, Any]:
    snapshot = db.get(ArticleSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.status != "complete":
        raise ValueError("Snapshot nicht gefunden oder nicht abgeschlossen")
    spec = ArticleRenumberSpec.model_validate(run.spec)
    candidates = resolve_scope(db, snapshot, spec)
    done = _existing_article_numbers(db, run.id)
    live_candidates = [c for c in candidates if c.article_number not in done]
    run.candidate_count = len(live_candidates) + len(done)
    if not live_candidates:
        run.status = "previewed"
        run.error = None
        run.case_variants = []
        run.word_positions = {}
        db.flush()
        from app.transform.summary import preview_summary

        return {
            "candidate_count": len(done),
            "changed_rows": 0,
            "word_positions": run.word_positions,
            "summary": preview_summary(run, changed_rows=0),
        }

    wc = client or weclapp_client_for(db, oid)
    try:
        ctx = prefetch_renumber_context(db, wc)
    except WeclappError as exc:
        abort = _auth_from_error(exc)
        if abort is not None:
            raise abort from exc
        raise

    shopify_skus = load_shopify_sku_set()
    reserved = seed_high_water(db)
    scheme = Scheme()
    try:
        fetched = fetch_live_articles(wc, live_candidates)
    except WeclappError as exc:
        abort = _auth_from_error(exc)
        if abort is not None:
            raise abort from exc
        raise

    eligible_count = 0
    rejected_count = 0
    shopify_warning_count = 0
    supply_source_warning_count = 0
    supply_example_lines: list[tuple[str, str, str]] = []
    changed = 0

    for candidate in live_candidates:
        weclapp_id = candidate.weclapp_id
        if not weclapp_id or weclapp_id in fetched.gone_ids:
            _add_gone(
                db,
                run,
                article_number=candidate.article_number,
                weclapp_id=weclapp_id or "",
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
            )
            db.commit()
            continue

        number = str(article.get("articleNumber") or candidate.article_number)
        version = str(article.get("version") or "")
        eligibility = evaluate_eligibility(
            article=article, weclapp_id=weclapp_id, ctx=ctx, db=db
        )
        destination = destination_pair_for_article(article, ctx)
        shopify_match = bool(shopify_skus is not None and number in shopify_skus)
        if shopify_match:
            shopify_warning_count += 1
        ss_warning = eligibility.supply_source_warning
        ss_warning_dicts = supply_source_warning_to_dict(ss_warning)
        if ss_warning_dicts:
            supply_source_warning_count += 1
            for item in ss_warning_dicts:
                supply_example_lines.append(
                    (
                        item.get("supplier_name") or "",
                        item.get("supplier_number") or "",
                        item.get("supplier_article_number") or "",
                    )
                )

        proposed = ""
        row_status = "REFUSED"
        reason_code = eligibility.reason_code
        if eligibility.ok and destination is not None:
            proposed = _allocate_number(reserved, destination, scheme) or ""
            if proposed:
                eligible_count += 1
                row_status = "CHANGED"
                changed += 1
            else:
                reason_code = "ineligible_no_change"
                rejected_count += 1
        else:
            rejected_count += 1

        dest_label = f"{destination[0]}.{destination[1]}" if destination else ""
        payload = {
            "kind": KIND,
            "destination_pair": dest_label,
            "proposed_number": proposed,
            "approved_number": None,
            "eligibility": eligibility.checks,
            "reason_code": reason_code,
            "reason_de": REASON_LABELS_DE.get(reason_code or "", reason_code or ""),
            "shopify_sku_match": shopify_match,
            "supply_source_warning": bool(ss_warning_dicts),
            "supply_source_warning_lines": ss_warning_dicts,
        }
        db.add(
            TransformRow(
                run_id=run.id,
                article_number=number,
                weclapp_id=weclapp_id,
                version_at_preview=version or None,
                field=FIELD,
                old_value=number,
                new_value=proposed or (REASON_LABELS_DE.get(reason_code or "", "—")),
                operations_fired=[payload],
                row_status=row_status,
            )
        )
        db.commit()

    run.status = "previewed"
    run.error = None
    run.case_variants = []
    run.word_positions = {
        "renumber": {
            "eligible": eligible_count,
            "rejected": rejected_count,
            "shopify_sku_warnings": shopify_warning_count,
            "supply_source_warnings": supply_source_warning_count,
            "summary_de": format_article_renumber_summary_de(
                eligible=eligible_count,
                rejected=rejected_count,
                shopify_warnings=shopify_warning_count,
                supply_source_warnings=supply_source_warning_count,
                supply_source_examples=supply_example_lines,
            ),
        }
    }
    db.flush()
    from app.transform.summary import preview_summary

    summary = preview_summary(run, changed_rows=changed)
    extra = run.word_positions.get("renumber", {})
    if extra.get("summary_de"):
        summary = str(extra["summary_de"]) + "\n\n" + summary
    return {
        "candidate_count": len(live_candidates) + len(done),
        "changed_rows": changed,
        "word_positions": run.word_positions,
        "summary": summary,
    }


def list_mismatch_candidates(
    db: Session,
    client: WeclappClient,
    *,
    snapshot: ArticleSnapshot,
    quellgruppe: str | None = None,
    zielgruppe: str | None = None,
) -> list[dict[str, Any]]:
    """All snapshot articles whose number pair differs from live category pair.

    Optional ``quellgruppe`` / ``zielgruppe`` are ``MMM.SSS`` pairs; filters apply
    while building the mismatch list (before any assistant row cap).
    """
    from app.transform.scope import ScopeCandidate

    row_query = select(ArticleSnapshotRow).where(ArticleSnapshotRow.snapshot_id == snapshot.id)
    if quellgruppe:
        row_query = row_query.where(
            ArticleSnapshotRow.article_number.like(f"{quellgruppe}.%")
        )
    rows = db.scalars(row_query)
    candidates = [
        ScopeCandidate(
            article_number=row.article_number,
            weclapp_id=row.weclapp_id or "",
        )
        for row in rows
        if row.weclapp_id and row.article_number
    ]
    ctx = prefetch_renumber_context(db, client)
    fetched = fetch_live_articles(client, candidates)
    mismatches: list[dict[str, Any]] = []
    for candidate in candidates:
        article = fetched.articles.get(candidate.weclapp_id)
        if not isinstance(article, dict):
            continue
        number_pair = parse_group_codes(article.get("articleNumber"))
        category_pair = destination_pair_for_article(article, ctx)
        if number_pair is None or category_pair is None or number_pair == category_pair:
            continue
        number_label = f"{number_pair[0]}.{number_pair[1]}"
        category_label = f"{category_pair[0]}.{category_pair[1]}"
        if quellgruppe and number_label != quellgruppe:
            continue
        if zielgruppe and category_label != zielgruppe:
            continue
        eligibility = evaluate_eligibility(
            article=article, weclapp_id=candidate.weclapp_id, ctx=ctx, db=db
        )
        mismatches.append(
            {
                "weclapp_id": candidate.weclapp_id,
                "article_number": str(article.get("articleNumber") or candidate.article_number),
                "number_pair": number_label,
                "category_pair": category_label,
                "eligibility": eligibility,
            }
        )
    return mismatches


def summarize_mismatch_eligibility(
    db: Session,
    client: WeclappClient,
    *,
    snapshot: ArticleSnapshot,
) -> dict[str, Any]:
    """Eligible count and per-check failure counts across the mismatch set."""
    mismatches = list_mismatch_candidates(db, client, snapshot=snapshot)
    check_keys = (
        "no_mismatch",
        "no_alias_row",
        "no_stock",
        "no_movement",
        "no_document",
        "registry_ok",
    )
    per_check_failures = {key: 0 for key in check_keys}
    supply_source_warning_count = 0
    eligible = 0
    for item in mismatches:
        eligibility: EligibilityResult = item["eligibility"]
        if eligibility.ok:
            eligible += 1
        if eligibility.supply_source_warning:
            supply_source_warning_count += 1
        for key in check_keys:
            if not eligibility.checks.get(key, False):
                per_check_failures[key] += 1
    return {
        "mismatch_total": len(mismatches),
        "eligible_hard_checks": eligible,
        "eligible_all_five": eligible,
        "supply_source_warnings": supply_source_warning_count,
        "per_check_failures": per_check_failures,
    }
