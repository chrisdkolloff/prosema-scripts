#!/usr/bin/env python3
"""One-off E2E smoke for admin renumber (110.010 -> 110.020 test article)."""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.article_renumber import ArticleRenumberSpec, approved_number_from_row
from app.assistant.catalog import snapshot_for_query
from app.auth import get_current_user
from app.db import SessionLocal, get_db
from app.jobs import HANDLERS
from app.main import app
from app.models import (
    ArticleSnapshotRow,
    AuditLog,
    Job,
    RetiredArticleNumber,
    TransformChunk,
    TransformRow,
    TransformRun,
    WeclappArticle,
)
from app.numbering_high_water import seed_high_water
from app.weclapp import weclapp_client_for
from core.numbering import Scheme

OID = "85156431-01ba-4bcf-844d-9243fd96e229"
TEST_NUMBER = "110.010.0220"
TEST_ID = "418774"

ADMIN: dict[str, Any] = {
    "oid": OID,
    "name": "Renumber Smoke Admin",
    "email": "smoke@prosema.local",
    "roles": ["user", "admin"],
}
USER_ONLY: dict[str, Any] = {
    "oid": OID,
    "name": "Renumber Smoke User",
    "email": "user@prosema.local",
    "roles": ["user"],
}


def _client(as_user: dict[str, Any]) -> TestClient:
    def override_user():
        return as_user

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _run_preview_job(db, run_id: str) -> None:
    job = db.scalars(
        select(Job)
        .where(Job.job_type == "article_transform_preview")
        .order_by(Job.created_at.desc())
    ).first()
    if job is None:
        raise RuntimeError("preview job missing")
    HANDLERS["article_transform_preview"](db, dict(job.payload or {}), OID)


def _run_apply_job(db) -> None:
    job = db.scalars(
        select(Job)
        .where(Job.job_type == "article_transform_apply")
        .order_by(Job.created_at.desc())
    ).first()
    if job is None:
        raise RuntimeError("apply job missing")
    HANDLERS["article_transform_apply"](db, dict(job.payload or {}), OID)


def start_preview_route(client: TestClient, snapshot_id: uuid.UUID) -> uuid.UUID:
    resp = client.post(
        f"/artikel-uebersicht/{snapshot_id}/renumber/vorschau",
        data={
            "renumber_scope": "selected",
            "artikelnummer": TEST_NUMBER,
        },
        follow_redirects=False,
    )
    if resp.status_code != 303:
        raise RuntimeError(f"preview start {resp.status_code} {resp.text[:500]}")
    loc = resp.headers["location"]
    run_id = uuid.UUID(loc.rstrip("/").split("/")[-1])
    return run_id


def confirm_route(client: TestClient, run_id: uuid.UUID, row_id: uuid.UUID) -> None:
    resp = client.post(
        f"/transform/{run_id}/bestaetigen",
        data={"zeile": [str(row_id)]},
        follow_redirects=False,
    )
    if resp.status_code != 303:
        raise RuntimeError(f"confirm {resp.status_code} {resp.text[:500]}")


def pipeline_once(*, label: str) -> dict[str, Any]:
    out: dict[str, Any] = {"label": label}
    with SessionLocal() as db:
        snap = snapshot_for_query(db)
        if snap is None:
            raise RuntimeError("no snapshot")
        client = _client(ADMIN)
        run_id = start_preview_route(client, snap.id)
        out["run_id"] = str(run_id)
        _run_preview_job(db, str(run_id))
        db.commit()
        run = db.get(TransformRun, run_id)
        out["run_status"] = run.status if run else None
        rows = list(
            db.scalars(
                select(TransformRow).where(
                    TransformRow.run_id == run_id,
                    TransformRow.article_number == TEST_NUMBER,
                )
            )
        )
        out["preview_rows"] = [
            {
                "status": r.row_status,
                "new_value": r.new_value,
                "payload": (r.operations_fired or [{}])[0],
            }
            for r in rows
        ]
        changed = [r for r in rows if r.row_status == "CHANGED"]
        if not changed:
            out["error"] = "no CHANGED row"
            app.dependency_overrides.clear()
            return out
        row = changed[0]
        out["proposed"] = approved_number_from_row(row)
        confirm_route(client, run_id, row.id)
        _run_apply_job(db)
        db.commit()
        db.refresh(row)
        out["apply_outcome"] = row.apply_outcome
        out["apply_detail"] = row.apply_detail
        app.dependency_overrides.clear()
    return out


def main() -> int:
    report: dict[str, Any] = {"test_number": TEST_NUMBER, "test_id": TEST_ID}

    # B.5 route gate (user only)
    with SessionLocal() as db:
        snap = snapshot_for_query(db)
        user_client = _client(USER_ONLY)
        resp = user_client.post(
            f"/artikel-uebersicht/{snap.id}/renumber/vorschau",
            data={"renumber_scope": "selected", "artikelnummer": TEST_NUMBER},
        )
        report["b5_preview_http"] = resp.status_code
        app.dependency_overrides.clear()

    # B.5 job gate
    try:
        HANDLERS["article_transform_apply"](
            db,
            {"transform_chunk_id": str(uuid.uuid4()), "requires_admin": True, "creator_roles": ["user"]},
            OID,
        )
        report["b5_job"] = "unexpected success"
    except ValueError as exc:
        report["b5_job"] = str(exc)

    # B.3 first successful apply
    report["first_apply"] = pipeline_once(label="success")

    # B.6 ineligible apply
    with SessionLocal() as db:
        client = weclapp_client_for(db, OID)
        art = client.get(f"/article/id/{TEST_ID}")
        # Add minimal supply source - need supplier. Discovery used POST articleSupplySource
        # For test: attach via PUT supplySources on article if supported, or create SS
        # User said add supply source in weclapp - use article PUT with supplySources array?
        # Safer: POST articleSupplySource with articleNumber
        suppliers = client.get("/party", params={"pageSize": 1, "supplier-eq": "true"})
        sup = ((suppliers or {}).get("result") or [{}])[0]
        sid = str(sup.get("id") or "")
        ss_body = {
            "articleNumber": TEST_NUMBER,
            "name": TEST_NUMBER,
            "supplierId": sid,
            "unitId": art.get("unitId"),
        }
        try:
            ss = client.post("/articleSupplySource", json=ss_body)
            report["b6_ss_id"] = ss.get("id") if isinstance(ss, dict) else ss
        except Exception as exc:
            report["b6_ss_error"] = str(exc)
            ss = None

    report["blocked_apply"] = pipeline_once(label="blocked")
    # remove SS
    with SessionLocal() as db:
        client = weclapp_client_for(db, OID)
        if report.get("b6_ss_id"):
            try:
                client.request("DELETE", f"/articleSupplySource/id/{report['b6_ss_id']}")
            except Exception:
                pass
        # also clear from article if embedded
        art = client.get(f"/article/id/{TEST_ID}")
        if live_ss := art.get("supplySources"):
            report["b6_cleanup_note"] = f"still has {len(live_ss)} supplySources on article"

    report["second_apply"] = pipeline_once(label="after_ss_removed")

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
