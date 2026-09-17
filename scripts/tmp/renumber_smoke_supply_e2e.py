#!/usr/bin/env python3
"""E2E smoke: renumber with supply source attached (preview → ack → apply → mirrors)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.assistant.catalog import snapshot_for_query
from app.auth import get_current_user
from app.db import SessionLocal, get_db
from app.jobs import HANDLERS
from app.main import app
from app.models import (
    Hauptgruppe,
    SupplierArticleAlias,
    TransformRow,
    TransformRun,
    Untergruppe,
    WeclappArticle,
    WeclappSupplySourceLink,
    Job,
)
from app.numbering_high_water import seed_high_water
from app.weclapp import weclapp_client_for
from app.weclapp_categories import find_coded_untergruppe_category, list_article_categories
from core.numbering import Scheme

OID = "85156431-01ba-4bcf-844d-9243fd96e229"
SRC = ("110", "010")
ADMIN: dict[str, Any] = {
    "oid": OID,
    "name": "Renumber SS Smoke",
    "email": "ss-smoke@prosema.local",
    "roles": ["user", "admin"],
}


def _client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: ADMIN

    def odb():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = odb
    return TestClient(app)


def main() -> int:
    report: dict[str, Any] = {}
    with SessionLocal() as db:
        h = db.scalars(select(Hauptgruppe).where(Hauptgruppe.code == SRC[0])).first()
        u_dst = db.scalars(
            select(Untergruppe).where(
                Untergruppe.hauptgruppe_id == h.id,
                Untergruppe.code == "020",
            )
        ).first()
        scheme = Scheme()
        reserved = seed_high_water(db)
        base = scheme.start if reserved.get(SRC) is None else reserved[SRC] + scheme.step
        nxt = base + scheme.step * 50
        test_number = scheme.format(*SRC, nxt)
        wc = weclapp_client_for(db, OID)
        cats = list_article_categories(wc)
        dest = find_coded_untergruppe_category(
            cats,
            haupt_name=h.name,
            haupt_code=h.code,
            unter_name=u_dst.name,
            unter_code=u_dst.code,
        )
        units = wc.get("/unit", params={"pageSize": 100, "name-eq": "Stk"})
        unit_id = str(((units or {}).get("result") or [{}])[0].get("id") or "3566")
        created = wc.post(
            "/article",
            json={
                "articleNumber": test_number,
                "name": "TEST SS RENUMBER E2E",
                "articleType": "BASIC",
                "unitId": unit_id,
                "taxRateType": "STANDARD",
                "active": False,
                "availableInSale": False,
                "articleCategoryId": str(dest["id"]),
            },
        )
        test_id = str(created.get("id"))
        report["created"] = {"id": test_id, "number": test_number}

        suppliers = wc.get("/party", params={"pageSize": 1, "supplier-eq": "true"})
        sid = str(((suppliers or {}).get("result") or [{}])[0].get("id") or "")
        art = wc.get(f"/article/id/{test_id}")
        try:
            ss = wc.post(
                "/articleSupplySource",
                json={
                    "articleNumber": test_number,
                    "name": test_number,
                    "supplierId": sid,
                    "unitId": art.get("unitId"),
                },
            )
        except Exception as exc:
            report["ss_post_error"] = str(exc)
            wc.request("DELETE", f"/article/id/{test_id}")
            print(json.dumps(report, indent=2, default=str))
            return 1
        ss_id = str(ss.get("id"))
        from app.supply_source_payload import build_article_attach_put

        body, params = build_article_attach_put(
            article_id=test_id,
            version=str(art.get("version") or ""),
            supply_sources=[{"articleSupplySourceId": ss_id, "positionNumber": 1}],
            primary_supply_source_id=ss_id,
        )
        wc.put(f"/article/id/{test_id}", params=params, json=body)

        from app.snapshots import pull_snapshot_rows
        from app.supply_source_index import pull_supply_source_index

        pull_supply_source_index(db, oid=OID)
        snap = snapshot_for_query(db)
        pull_snapshot_rows(db, snap, oid=OID)
        db.commit()
        tc = _client()
        resp = tc.post(
            f"/artikel-uebersicht/{snap.id}/renumber/vorschau",
            data={"renumber_scope": "selected", "artikelnummer": test_number},
            follow_redirects=False,
        )
        run_id = uuid.UUID(resp.headers["location"].rstrip("/").split("/")[-1])
        job = db.scalars(
            select(Job)
            .where(Job.job_type == "article_transform_preview")
            .order_by(Job.created_at.desc())
        ).first()
        HANDLERS["article_transform_preview"](db, dict(job.payload or {}), OID)
        db.commit()
        run = db.get(TransformRun, run_id)
        meta = (run.word_positions or {}).get("renumber") or {}
        report["preview_meta"] = meta
        row = db.scalars(
            select(TransformRow).where(
                TransformRow.run_id == run_id,
                TransformRow.article_number == test_number,
            )
        ).first()
        report["row_status"] = row.row_status if row else None
        payload = (row.operations_fired or [{}])[0] if row else {}
        report["supply_source_warning"] = payload.get("supply_source_warning")

        confirm_data: dict[str, str] = {"zeile": [str(row.id)]}
        if meta.get("supply_source_warnings"):
            confirm_data["supply_source_warnung_bestaetigt"] = "1"
        resp2 = tc.post(
            f"/transform/{run_id}/bestaetigen",
            data=confirm_data,
            follow_redirects=False,
        )
        report["confirm_http"] = resp2.status_code
        job2 = db.scalars(
            select(Job)
            .where(Job.job_type == "article_transform_apply")
            .order_by(Job.created_at.desc())
        ).first()
        HANDLERS["article_transform_apply"](db, dict(job2.payload or {}), OID)
        db.commit()
        db.refresh(row)
        report["apply_outcome"] = row.apply_outcome
        new_number = row.new_value
        report["new_number"] = new_number
        mirror = db.get(WeclappArticle, test_id)
        report["mirror_article_number"] = mirror.article_number if mirror else None
        links = list(
            db.scalars(
                select(WeclappSupplySourceLink).where(
                    WeclappSupplySourceLink.weclapp_article_id == test_id
                )
            )
        )
        report["link_numbers"] = [link.article_number for link in links]
        aliases = list(
            db.scalars(
                select(SupplierArticleAlias).where(
                    SupplierArticleAlias.weclapp_article_id == test_id,
                    SupplierArticleAlias.source == "supply_source",
                )
            )
        )
        report["alias_numbers"] = [a.article_number for a in aliases]

        try:
            wc.request("DELETE", f"/articleSupplySource/id/{ss_id}")
        except Exception:
            pass
        try:
            wc.request("DELETE", f"/article/id/{test_id}")
        except Exception:
            pass
        app.dependency_overrides.clear()

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
