#!/usr/bin/env python3
"""Phase 1 dry-run: eligibility stats + optional preview without apply."""

from __future__ import annotations

import argparse
import json
import sys

from app.assistant.catalog import snapshot_for_query
from app.db import SessionLocal
from app.article_renumber import (
    ArticleRenumberSpec,
    list_mismatch_candidates,
    run_article_renumber_preview,
    summarize_mismatch_eligibility,
)
from app.models import TransformRun
from app.transform.schemas import TransformScope
from app.weclapp import weclapp_client_for


def main() -> int:
    parser = argparse.ArgumentParser(description="Admin renumber Phase 1 report")
    parser.add_argument(
        "--oid",
        required=True,
        help="Entra user oid with weclapp token",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Run preview job logic synchronously (no apply)",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        snapshot = snapshot_for_query(db)
        if snapshot is None:
            print("No complete current snapshot.", file=sys.stderr)
            return 1
        client = weclapp_client_for(db, args.oid)
        stats = summarize_mismatch_eligibility(db, client, snapshot=snapshot)
        print("=== Eligibility (mismatch set) ===")
        print(json.dumps(stats, indent=2, ensure_ascii=False))

        mismatches = list_mismatch_candidates(db, client, snapshot=snapshot)
        print(f"\nMismatch articles: {len(mismatches)}")

        if args.preview:
            numbers = [m["article_number"] for m in mismatches]
            if not numbers:
                print("No mismatches — skipping preview.")
                return 0
            spec = ArticleRenumberSpec(scope=TransformScope(article_numbers=numbers))
            run = TransformRun(
                created_by_oid=args.oid,
                snapshot_id=snapshot.id,
                spec=spec.model_dump(mode="json"),
                status="previewing",
            )
            db.add(run)
            db.flush()
            result = run_article_renumber_preview(db, run, oid=args.oid, client=client)
            print("\n=== Dry-run preview ===")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("\n(preview rolled back — no TransformRun persisted)")
            db.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
