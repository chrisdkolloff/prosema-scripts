"""Explicit, reviewable article assignments; registration batches only suggest IDs."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batches import effective_values
from app.models import ArticleBatch, ArticleBatchRow, SupplierArticleAlias, WeclappArticle
from app.supply_source_runs import (
    SupplySourceRunError,
    assert_editable,
    attach_manual_alias,
    load_rows,
)


def match_preview(db: Session, run, batch_id: str = "") -> dict:
    missing = [
        r for r in load_rows(db, run.id) if not r.weclapp_article_id and r.row_intent != "skip"
    ]
    batches = (
        list(
            db.scalars(
                select(ArticleBatch)
                .where(ArticleBatch.status == "submitted")
                .order_by(ArticleBatch.submitted_at.desc())
                .limit(50)
            )
        )
        if missing
        else []
    )
    candidates = {}
    if batch_id:
        try:
            bid = UUID(batch_id)
        except ValueError as exc:
            raise SupplySourceRunError("Ungültiger Artikel-Batch.") from exc
        batch = db.get(ArticleBatch, bid)
        if batch is None or batch.status != "submitted":
            raise SupplySourceRunError("Nur erfolgreich gesendete Artikel-Batches sind zulässig.")
        for source in db.scalars(
            select(ArticleBatchRow).where(
                ArticleBatchRow.batch_id == bid,
                ArticleBatchRow.weclapp_article_id.is_not(None),
            )
        ):
            payload = source.approved_payload or {}
            number = str(payload.get("articleNumber") or "").strip()
            san = effective_values(source).get("Lieferantenartikelnummer", "").strip()
            article = db.get(WeclappArticle, source.weclapp_article_id)
            if not san or not number or article is None or article.missing_since is not None:
                continue
            if article.article_number != number:
                continue
            candidates.setdefault(san, set()).add(number)
    return {
        "batches": batches,
        "batch_id": batch_id,
        "rows": [
            {
                "id": r.id,
                "san": r.supplier_article_number,
                "name": r.name or "",
                "number": next(iter(candidates[r.supplier_article_number]))
                if len(candidates.get(r.supplier_article_number, set())) == 1
                else "",
            }
            for r in missing
        ],
    }


def assign_missing(db: Session, run, selections: dict[int, str], user) -> int:
    assert_editable(run)
    rows = {r.id: r for r in load_rows(db, run.id)}
    planned = []
    seen_sans = set()
    for row_id, raw in selections.items():
        number = raw.strip()
        if not number:
            continue
        row = rows.get(row_id)
        if row is None or row.weclapp_article_id or row.row_intent == "skip":
            raise SupplySourceRunError(
                "Die Zeile ist nicht mehr ohne Artikelzuordnung. Bitte neu laden."
            )
        if row.supplier_article_number in seen_sans:
            raise SupplySourceRunError(
                "Lieferantenartikelnummer mehrfach ausgewählt. Bitte einzeln prüfen."
            )
        seen_sans.add(row.supplier_article_number)
        articles = list(
            db.scalars(
                select(WeclappArticle).where(
                    WeclappArticle.article_number == number,
                    WeclappArticle.missing_since.is_(None),
                )
            )
        )
        if len(articles) != 1:
            raise SupplySourceRunError(
                f"Artikel {number} ist im aktuellen weclapp-Index nicht eindeutig vorhanden."
            )
        aliases = list(
            db.scalars(
                select(SupplierArticleAlias).where(
                    SupplierArticleAlias.supplier_id == run.supplier_id,
                    SupplierArticleAlias.supplier_article_number == row.supplier_article_number,
                )
            )
        )
        if any(a.weclapp_article_id != articles[0].weclapp_article_id for a in aliases):
            raise SupplySourceRunError(
                f"Für {row.supplier_article_number} besteht bereits eine andere Zuordnung."
            )
        planned.append((row, number))
    if not planned:
        raise SupplySourceRunError("Bitte mindestens eine PROSEMA-Artikelnummer angeben.")
    # All assignments are validated before the first change; one transaction for the form.
    for row, number in planned:
        attach_manual_alias(
            db,
            run,
            row,
            article_number=number,
            oid=str(user["oid"]),
            name=str(user.get("name") or user["oid"]),
            commit=False,
        )
    db.commit()
    return len(planned)
