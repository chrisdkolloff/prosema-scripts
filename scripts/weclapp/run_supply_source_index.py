"""Run a read-only weclapp supply-source index build using .env credentials."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from app.db import SessionLocal
from app.models import (
    Supplier,
    SupplierDiscountCategory,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
)
from app.supply_source_index import pull_supply_source_index
from scripts.weclapp.client import WeclappClient
from scripts.weclapp.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supplier-number", default=None)
    args = parser.parse_args(argv)

    config = load_config()
    client = WeclappClient(config)
    db = SessionLocal()
    supplier_id = None
    if args.supplier_number:
        row = db.scalars(
            select(Supplier).where(Supplier.supplier_number == args.supplier_number)
        ).first()
        if row is None:
            print(f"supplier {args.supplier_number} not in suppliers", file=sys.stderr)
            return 1
        supplier_id = row.id
    try:
        result = pull_supply_source_index(
            db, oid="script", supplier_id=supplier_id, client=client
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    counts = {
        "suppliers": db.scalar(select(func.count()).select_from(Supplier)),
        "discount_categories": db.scalar(
            select(func.count()).select_from(SupplierDiscountCategory)
        ),
        "articles": db.scalar(select(func.count()).select_from(WeclappArticle)),
        "supply_sources": db.scalar(
            select(func.count()).select_from(WeclappSupplySource)
        ),
        "links": db.scalar(select(func.count()).select_from(WeclappSupplySourceLink)),
        "orphans": db.scalar(
            text(
                """
                SELECT count(*) FROM weclapp_supply_sources ss
                WHERE NOT EXISTS (
                    SELECT 1 FROM weclapp_supply_source_links l
                    WHERE l.supply_source_weclapp_id = ss.weclapp_id
                )
                """
            )
        ),
    }
    shared = db.execute(
        text(
            """
            SELECT ss.supplier_article_number,
                   array_agg(l.article_number ORDER BY l.article_number)
            FROM weclapp_supply_source_links l
            JOIN weclapp_supply_sources ss
              ON ss.weclapp_id = l.supply_source_weclapp_id
            GROUP BY ss.weclapp_id, ss.supplier_article_number
            HAVING count(*) > 1
            ORDER BY ss.supplier_article_number
            """
        )
    ).all()
    print(json.dumps({"result": result, "counts": {k: int(v or 0) for k, v in counts.items()},
                      "shared": [{"san": r[0], "articles": list(r[1])} for r in shared],
                      "ran_at": datetime.now(UTC).isoformat()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
