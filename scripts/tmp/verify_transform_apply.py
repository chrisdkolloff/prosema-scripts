"""Manual apply of a transform preview against 999.999 articles only.

Dry-run (default): preview + print summary, no PUT, no approval.

    PYTHONPATH=. python scripts/tmp/verify_transform_apply.py

Write (preview, approve chunk 0, apply, restore names):

    PYTHONPATH=. python scripts/tmp/verify_transform_apply.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from typing import Any

from sqlalchemy import select

from app.article_write import GUARD_PREFIX, update_article
from app.db import SessionLocal
from app.models import (
    ArticleSnapshot,
    ArticleSnapshotRow,
    AuditLog,
    TransformRun,
    UserWeclappToken,
)
from app.transform.apply import apply_chunk, approve_chunk
from app.transform.preview import run_preview
from app.transform.schemas import TransformSpec
from app.transform.summary import chunk_result_summary, preview_summary
from app.weclapp import weclapp_client_for
from core.article_write_fields import CustomAttributeResolver
from scripts.weclapp.client import WeclappError

MARKER = " [TRANSFORM-APPLY-TEST]"
ACTOR_OID = "script-transform-apply-verify"
ACTOR_NAME = "verify_transform_apply.py"


def _latest_snapshot(db) -> ArticleSnapshot:
    snap = db.scalars(
        select(ArticleSnapshot)
        .where(
            ArticleSnapshot.status == "complete",
            ArticleSnapshot.weclapp_tenant == "prosema",
        )
        .order_by(ArticleSnapshot.created_at.desc())
    ).first()
    if snap is None:
        raise SystemExit("Kein abgeschlossener Snapshot")
    return snap


def _guarded_articles(db, snapshot: ArticleSnapshot, client: Any) -> list[dict]:
    rows = list(
        db.scalars(
            select(ArticleSnapshotRow).where(
                ArticleSnapshotRow.snapshot_id == snapshot.id,
                ArticleSnapshotRow.article_number.like(f"{GUARD_PREFIX}%"),
            )
        )
    )
    found: list[dict] = []
    for row in rows:
        if not row.weclapp_id:
            continue
        article = client.get(f"/article/id/{row.weclapp_id}")
        if not isinstance(article, dict):
            continue
        number = str(article.get("articleNumber") or "")
        if not number.startswith(GUARD_PREFIX):
            continue
        found.append(article)
        if len(found) >= 2:
            break
    if not found:
        raise SystemExit("Keine 999.999-Artikel im Snapshot")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        token_rows = list(
            db.scalars(
                select(UserWeclappToken).order_by(
                    UserWeclappToken.last_verified_ok.desc().nullslast(),
                    UserWeclappToken.updated_at.desc(),
                )
            )
        )
        client = None
        for row in token_rows:
            try:
                candidate = weclapp_client_for(db, row.oid)
                candidate.get("/article/id/353023")
            except (WeclappError, Exception):
                continue
            client = candidate
            break
        if client is None:
            raise SystemExit("Kein gültiges weclapp-Token (401/403 auf Probe-GET)")
        snapshot = _latest_snapshot(db)
        articles = _guarded_articles(db, snapshot, client)
        first = articles[0]
        number = str(first["articleNumber"])
        weclapp_id = str(first["id"])
        live_name = str(first.get("name") or "")
        live_kurz = str(first.get("shortDescription1") or "")
        if not live_name:
            raise SystemExit("Artikelname leer")
        originals = {"Prosema-Artikelname": live_name, "Kurzbeschreibung": live_kurz}
        operations = [
            {
                "op": "replace_literal",
                "search": live_name,
                "replace": live_name + MARKER,
            }
        ]
        if live_kurz and live_kurz != live_name:
            operations.append(
                {
                    "op": "replace_literal",
                    "search": live_kurz,
                    "replace": live_kurz + MARKER,
                }
            )
        spec = TransformSpec.model_validate(
            {
                "scope": {"article_numbers": [number]},
                "fields": ["Prosema-Artikelname", "Kurzbeschreibung"],
                "operations": operations,
            }
        )
        run = TransformRun(
            created_by_oid=ACTOR_OID,
            snapshot_id=snapshot.id,
            spec=spec.model_dump(mode="json"),
            status="previewing",
            word_positions={},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        result = run_preview(db, run, oid=ACTOR_OID, client=client)
        db.commit()
        db.refresh(run)
        print("== Vorschau ==")
        print(preview_summary(run, changed_rows=result["changed_rows"]))
        print("changed_rows", result["changed_rows"])
        print("word_positions", run.word_positions)
        if result["changed_rows"] < 2:
            raise SystemExit("Vorschau hat weniger als 2 CHANGED-Zeilen")
        if not args.apply:
            print("\nKein --apply: keine Bestätigung, kein PUT.")
            return 0

        chunk = approve_chunk(db, run, chunk_index=0, approver_oid=ACTOR_OID)
        db.commit()
        print("\n== Anwenden chunk 0 ==")
        apply_chunk(
            db,
            chunk,
            oid=ACTOR_OID,
            actor_name=ACTOR_NAME,
            client=client,
        )
        db.refresh(chunk)
        print(chunk_result_summary(db, chunk))
        print("\n== Audit ==")
        try:
            audits = list(
                db.scalars(
                    select(AuditLog)
                    .where(
                        AuditLog.entity_type == "weclapp_article",
                        AuditLog.actor_oid == ACTOR_OID,
                    )
                    .order_by(AuditLog.occurred_at.desc())
                )
            )
            for row in audits:
                if (row.detail or {}).get("transform_run_id") != str(run.id):
                    continue
                print(
                    row.action,
                    row.entity_id,
                    row.detail.get("article_number"),
                    row.detail.get("transform_run_id"),
                    row.detail.get("transform_chunk_id"),
                )
        except Exception as exc:
            print("audit listing failed:", exc)

        resolver = CustomAttributeResolver(client)
        update_article(
            db=db,
            client=client,
            resolver=resolver,
            article_id=weclapp_id,
            changes=originals,
            actor_oid=ACTOR_OID,
            actor_name=ACTOR_NAME,
        )
        db.commit()
        print("restored", number)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
