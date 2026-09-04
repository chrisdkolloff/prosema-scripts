"""Manual verification of app.article_write against 999.999.001 only.

Read-only unless --apply is given. Restores the original name at the end.

    PYTHONPATH=. python scripts/tmp/verify_article_write.py
    PYTHONPATH=. python scripts/tmp/verify_article_write.py --apply
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from app.article_write import ArticleWriteOutcome, update_article
from app.db import SessionLocal
from app.models import AuditLog
from core.article_write_fields import CustomAttributeResolver
from scripts.weclapp.client import WeclappClient
from scripts.weclapp.config import load_config

TARGET = "999.999.001"
GUARD_PREFIX = "999.999"
ACTOR_OID = "script-article-write-verify"
ACTOR_NAME = "verify_article_write.py"


class CountingClient:
    def __init__(self, inner: WeclappClient) -> None:
        self.inner = inner
        self.gets = 0
        self.puts = 0

    def get(self, path: str, *, params=None) -> Any:
        self.gets += 1
        return self.inner.get(path, params=params)

    def put(self, path: str, *, params=None, json=None) -> Any:
        self.puts += 1
        return self.inner.put(path, params=params, json=json)

    def iter_pages(self, entity: str, *, params=None, page_size=None):
        return self.inner.iter_pages(entity, params=params, page_size=page_size)


class StaleGetClient(CountingClient):
    def __init__(self, inner: WeclappClient, stale_article: dict[str, Any]) -> None:
        super().__init__(inner)
        self._stale = stale_article

    def get(self, path: str, *, params=None) -> Any:
        self.gets += 1
        if path.startswith("/article/id/"):
            return copy.deepcopy(self._stale)
        return self.inner.get(path, params=params)


def fetch(client: WeclappClient) -> dict[str, Any]:
    matches = list(client.iter_pages("article", params={"articleNumber-eq": TARGET}))
    if len(matches) != 1:
        raise SystemExit(f"Expected 1 article {TARGET!r}, got {len(matches)}")
    article = matches[0]
    number = str(article.get("articleNumber") or "")
    if not number.startswith(GUARD_PREFIX):
        raise SystemExit(f"Refusing {number!r}")
    return article


def print_result(label: str, result, puts: int) -> None:
    print(f"\n== {label} ==")
    print(f"  outcome={result.outcome.value} put_sent={result.put_sent} puts={puts}")
    print(f"  version {result.version_before} -> {result.version_after}")
    print(f"  message={result.message}")
    if result.audit is not None:
        print("  audit:", json.dumps(result.audit.model_dump(mode="json"), ensure_ascii=False))


def print_audit_rows(db) -> None:
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.actor_oid == ACTOR_OID)
        .order_by(AuditLog.occurred_at)
    ).all()
    print("\n== audit_log rows ==")
    for row in rows:
        print(
            json.dumps(
                {
                    "action": row.action,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "detail": row.detail,
                },
                ensure_ascii=False,
                default=str,
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    real = WeclappClient(load_config())
    article = fetch(real)
    article_id = str(article["id"])
    original_name = str(article.get("name") or "")
    print(f"target {TARGET} id={article_id} version={article.get('version')!r}")
    print(f"current name: {original_name}")

    if not args.apply:
        print("Dry run. Pass --apply to PUT 999.999.001 and write audit_log.")
        return 0

    verify_name = f"Rippenfolie WRITE-VERIFY {int(time.time())}"
    db = SessionLocal()
    resolver = CustomAttributeResolver(real)
    try:
        counted = CountingClient(real)
        updated = update_article(
            db=db,
            client=counted,
            resolver=resolver,
            article_id=article_id,
            changes={"Prosema-Artikelname": verify_name},
            actor_oid=ACTOR_OID,
            actor_name=ACTOR_NAME,
        )
        db.commit()
        print_result("change name", updated, counted.puts)
        if updated.outcome is not ArticleWriteOutcome.UPDATED:
            raise SystemExit("expected UPDATED")
        if counted.puts != 1:
            raise SystemExit(f"expected 1 PUT, got {counted.puts}")

        counted2 = CountingClient(real)
        same = update_article(
            db=db,
            client=counted2,
            resolver=resolver,
            article_id=article_id,
            changes={"Prosema-Artikelname": verify_name},
            actor_oid=ACTOR_OID,
            actor_name=ACTOR_NAME,
        )
        db.commit()
        print_result("same name again", same, counted2.puts)
        if same.outcome is not ArticleWriteOutcome.UNCHANGED:
            raise SystemExit("expected UNCHANGED")
        if counted2.puts != 0:
            raise SystemExit("UNCHANGED must not PUT")

        fresh = real.get(f"/article/id/{article_id}")
        stale = copy.deepcopy(fresh)
        bump_name = verify_name + " bump"
        real.put(
            f"/article/id/{article_id}",
            params={"ignoreMissingProperties": "true"},
            json={"name": bump_name, "version": str(fresh["version"])},
        )
        stale_client = StaleGetClient(real, stale)
        conflict = update_article(
            db=db,
            client=stale_client,
            resolver=resolver,
            article_id=article_id,
            changes={"Prosema-Artikelname": verify_name + " conflict"},
            actor_oid=ACTOR_OID,
            actor_name=ACTOR_NAME,
        )
        db.commit()
        print_result("stale version", conflict, stale_client.puts)
        if conflict.outcome is not ArticleWriteOutcome.CONFLICT:
            raise SystemExit(f"expected CONFLICT, got {conflict.outcome}")
        if stale_client.puts != 1:
            raise SystemExit("CONFLICT should PUT once, not retry")

        counted3 = CountingClient(real)
        refused = update_article(
            db=db,
            client=counted3,
            resolver=resolver,
            article_id=article_id,
            changes={"Prosema-Artikelnummer": "999.999.999"},
            actor_oid=ACTOR_OID,
            actor_name=ACTOR_NAME,
        )
        db.commit()
        print_result("forbidden key", refused, counted3.puts)
        if refused.outcome is not ArticleWriteOutcome.REFUSED:
            raise SystemExit("expected REFUSED")
        if counted3.gets or counted3.puts:
            raise SystemExit(
                f"REFUSED must not call article GET/PUT (gets={counted3.gets} puts={counted3.puts})"
            )

        print_audit_rows(db)
    finally:
        live = real.get(f"/article/id/{article_id}")
        if str(live.get("name") or "") != original_name:
            real.put(
                f"/article/id/{article_id}",
                params={"ignoreMissingProperties": "true"},
                json={"name": original_name, "version": str(live["version"])},
            )
            print(f"\nrestored name to: {original_name}")
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
