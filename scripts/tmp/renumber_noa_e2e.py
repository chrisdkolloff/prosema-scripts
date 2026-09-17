#!/usr/bin/env python3
"""E2E: synthetic article through Noa renumber tools + UI apply."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.article_renumber import approved_number_from_row
from app.assistant.service import ask
from app.assistant.catalog import snapshot_for_query
from app.auth import get_current_user
from app.db import SessionLocal, get_db
from app.jobs import HANDLERS
from app.main import app
from app.models import (
    ArticleSnapshotRow,
    AuditLog,
    Hauptgruppe,
    RetiredArticleNumber,
    TransformRow,
    TransformRun,
    Job,
    Untergruppe,
    WeclappArticle,
)
from app.numbering_high_water import seed_high_water
from app.snapshots import pull_snapshot_rows
from app.supply_source_index import pull_supply_source_index
from app.transform.ui import proposed_spec_from_tool_calls
from app.weclapp import weclapp_client_for
from app.weclapp_categories import find_coded_untergruppe_category, list_article_categories
from core.numbering import Scheme

OID = "85156431-01ba-4bcf-844d-9243fd96e229"
SRC = ("110", "010")
ADMIN: dict[str, Any] = {
    "oid": OID,
    "name": "Noa Renumber E2E",
    "email": "noa-e2e@prosema.local",
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
        h = db.scalars(select(Hauptgruppe).where(Hauptgruppe.code == "110")).first()
        u_dst = db.scalars(
            select(Untergruppe).where(
                Untergruppe.hauptgruppe_id == h.id, Untergruppe.code == "020"
            )
        ).first()
        scheme = Scheme()
        reserved = seed_high_water(db)
        nxt = scheme.start if reserved.get(SRC) is None else reserved[SRC] + scheme.step
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
                "name": "TEST NOA RENUMBER - NICHT VERWENDEN",
                "articleType": "BASIC",
                "unitId": unit_id,
                "taxRateType": "STANDARD",
                "active": False,
                "availableInSale": False,
                "articleCategoryId": str(dest["id"]),
            },
        )
        test_id = str(created.get("id"))
        report["created"] = {"number": test_number, "id": test_id}

        idx = pull_supply_source_index(db, oid=OID)
        mirror = db.get(WeclappArticle, test_id)
        report["mirror_before"] = mirror.article_number if mirror else None
        if mirror is None:
            print(json.dumps(report, indent=2))
            return 1

        snap = snapshot_for_query(db)
        pull_snapshot_rows(db, snap, oid=OID)
        db.commit()

        k = ask(
            db,
            ADMIN,
            f"Ist der Artikel {test_number} unter den Kandidaten für Umnummerierung und berechtigt?",
            write_mode=True,
        )
        report["noa_kandidaten"] = {
            "outcome": k.outcome,
            "answer": k.answer_de,
            "total_count": k.total_count,
        }
        audit_k = db.get(__import__("app.models", fromlist=["AssistantQuery"]).AssistantQuery, k.audit_id)
        report["noa_kandidaten_tools"] = audit_k.tool_calls if audit_k else []

        v = ask(
            db,
            ADMIN,
            f"Schlage vor, den Artikel {test_number} neu zu nummerieren (Nummer an Kategorie anpassen).",
            write_mode=True,
        )
        audit_v = db.get(__import__("app.models", fromlist=["AssistantQuery"]).AssistantQuery, v.audit_id)
        spec = proposed_spec_from_tool_calls(audit_v.tool_calls if audit_v else [])
        report["noa_vorschlagen"] = {
            "outcome": v.outcome,
            "answer": v.answer_de,
            "spec_kind": spec.model_dump(mode="json").get("kind") if spec else None,
        }

        if spec is None:
            print(json.dumps(report, indent=2, default=str))
            return 1

        tc = _client()
        resp = tc.post(
            f"/artikel-uebersicht/{snap.id}/transform/vorschau-vorschlag",
            data={"spec_json": json.dumps(spec.model_dump(mode="json"))},
            follow_redirects=False,
        )
        report["preview_http"] = resp.status_code
        run_id = uuid.UUID(resp.headers["location"].rstrip("/").split("/")[-1])
        job = db.scalars(
            select(Job)
            .where(Job.job_type == "article_transform_preview")
            .order_by(Job.created_at.desc())
        ).first()
        HANDLERS["article_transform_preview"](db, dict(job.payload or {}), OID)
        db.commit()
        row = db.scalars(
            select(TransformRow).where(
                TransformRow.run_id == run_id,
                TransformRow.article_number == test_number,
            )
        ).first()
        new_number = approved_number_from_row(row) if row else ""
        report["proposed"] = new_number
        resp2 = tc.post(
            f"/transform/{run_id}/bestaetigen",
            data={"zeile": [str(row.id)]},
            follow_redirects=False,
        )
        report["confirm_http"] = resp2.status_code
        job = db.scalars(
            select(Job)
            .where(Job.job_type == "article_transform_apply")
            .order_by(Job.created_at.desc())
        ).first()
        HANDLERS["article_transform_apply"](db, dict(job.payload or {}), OID)
        db.commit()
        app.dependency_overrides.clear()

        mirror = db.get(WeclappArticle, test_id)
        snap_row = db.scalars(
            select(ArticleSnapshotRow).where(
                ArticleSnapshotRow.snapshot_id == snap.id,
                ArticleSnapshotRow.weclapp_id == test_id,
            )
        ).first()
        retired = list(
            db.scalars(
                select(RetiredArticleNumber).where(
                    RetiredArticleNumber.weclapp_article_id == test_id
                )
            )
        )
        audit_n = db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "article")
            .order_by(AuditLog.occurred_at.desc())
            .limit(3)
        ).all()
        report["verify"] = {
            "weclapp_live": wc.get(f"/article/id/{test_id}").get("articleNumber"),
            "weclapp_articles": mirror.article_number if mirror else None,
            "snapshot_row": snap_row.article_number if snap_row else None,
            "retired": [(r.retired_number, r.new_number) for r in retired],
            "audit_recent": len(audit_n),
        }
        report["ok"] = (
            mirror is not None
            and mirror.article_number == new_number
            and snap_row is not None
            and snap_row.article_number == new_number
            and retired
        )

        try:
            wc.request("DELETE", f"/article/id/{test_id}")
        except Exception as exc:
            report["delete_err"] = str(exc)
        db.execute(
            delete(RetiredArticleNumber).where(RetiredArticleNumber.weclapp_article_id == test_id)
        )
        db.commit()
        pull_snapshot_rows(db, snap, oid=OID)
        db.commit()
        report["index_elapsed"] = idx.get("elapsed_seconds")

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
