#!/usr/bin/env python3
"""Phase A: live weclapp probe — renumber with supply source attached (synthetic article only)."""

from __future__ import annotations

import json
import sys
from typing import Any

from sqlalchemy import select

from app.article_renumber_write import build_article_number_put
from app.db import SessionLocal
from app.models import Hauptgruppe, Untergruppe
from app.numbering_high_water import seed_high_water
from app.weclapp import weclapp_client_for
from app.weclapp_categories import find_coded_untergruppe_category, list_article_categories
from core.numbering import Scheme

OID = "85156431-01ba-4bcf-844d-9243fd96e229"
SRC = ("110", "010")
PROBE_NEW_SUFFIX = "0999"  # temporary probe suffix within same untergruppe prefix


def _ss_snapshot(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "supplySources": article.get("supplySources"),
        "primarySupplySourceId": article.get("primarySupplySourceId"),
    }


def _compare(before: dict[str, Any], after: dict[str, Any]) -> str:
    b = _ss_snapshot(before)
    a = _ss_snapshot(after)
    if b == a:
        return "unchanged"
    if not a.get("supplySources") and not a.get("primarySupplySourceId"):
        return "cleared"
    return "changed"


def _create_test_article(db, client) -> tuple[str, str, str]:
    """Returns (weclapp_id, article_number, probe_new_number)."""
    h = db.scalars(select(Hauptgruppe).where(Hauptgruppe.code == SRC[0])).first()
    u_src = db.scalars(
        select(Untergruppe).where(
            Untergruppe.hauptgruppe_id == h.id,
            Untergruppe.code == SRC[1],
        )
    ).first()
    u_dst = db.scalars(
        select(Untergruppe).where(
            Untergruppe.hauptgruppe_id == h.id,
            Untergruppe.code == "020",
        )
    ).first()
    scheme = Scheme()
    reserved = seed_high_water(db)
    nxt = scheme.start if reserved.get(SRC) is None else reserved[SRC] + scheme.step
    test_number = scheme.format(*SRC, nxt)
    probe_new = f"{SRC[0]}.{SRC[1]}.{PROBE_NEW_SUFFIX}"
    cats = list_article_categories(client)
    dest = find_coded_untergruppe_category(
        cats,
        haupt_name=h.name,
        haupt_code=h.code,
        unter_name=u_dst.name,
        unter_code=u_dst.code,
    )
    units = client.get("/unit", params={"pageSize": 100, "name-eq": "Stk"})
    unit_id = str(((units or {}).get("result") or [{}])[0].get("id") or "3566")
    created = client.post(
        "/article",
        json={
            "articleNumber": test_number,
            "name": "TEST RENUMBER SS PROBE - NICHT VERWENDEN",
            "articleType": "BASIC",
            "unitId": unit_id,
            "taxRateType": "STANDARD",
            "active": False,
            "availableInSale": False,
            "articleCategoryId": str(dest["id"]),
        },
    )
    return str(created.get("id")), test_number, probe_new


def main() -> int:
    report: dict[str, Any] = {}

    with SessionLocal() as db:
        client = weclapp_client_for(db, OID)
        test_id, test_number, probe_new = _create_test_article(db, client)
        report["test_id"] = test_id
        report["test_number"] = test_number
        report["probe_new_number"] = probe_new

        art = client.get(f"/article/id/{test_id}")
        if not isinstance(art, dict):
            print(json.dumps({"error": "GET article failed"}, indent=2))
            return 1
        report["initial_number"] = art.get("articleNumber")
        report["initial_ss"] = _ss_snapshot(art)

        # Attach supply source if missing
        ss_id = None
        if not art.get("supplySources"):
            suppliers = client.get("/party", params={"pageSize": 1, "supplier-eq": "true"})
            sup = ((suppliers or {}).get("result") or [{}])[0]
            sid = str(sup.get("id") or "")
            ss_body = {
                "articleNumber": str(art.get("articleNumber") or test_number),
                "name": str(art.get("articleNumber") or test_number),
                "supplierId": sid,
                "unitId": art.get("unitId"),
            }
            ss = client.post("/articleSupplySource", json=ss_body)
            ss_id = str(ss.get("id") or "") if isinstance(ss, dict) else ""
            report["created_ss_id"] = ss_id
            # Link to article via PUT (weclapp pairing)
            art = client.get(f"/article/id/{test_id}")
            from app.supply_source_payload import build_article_attach_put

            body, params = build_article_attach_put(
                article_id=test_id,
                version=str(art.get("version") or ""),
                supply_sources=[{"articleSupplySourceId": ss_id, "positionNumber": 1}],
                primary_supply_source_id=ss_id,
            )
            client.put(f"/article/id/{test_id}", params=params, json=body)
            art = client.get(f"/article/id/{test_id}")

        report["step1"] = _ss_snapshot(art)
        report["step1_article_number"] = art.get("articleNumber")

        version = str(art.get("version") or "")
        current_number = str(art.get("articleNumber") or test_number)

        # Step 2: narrow PUT
        step2_error = None
        try:
            client.put(
                f"/article/id/{test_id}",
                params={"ignoreMissingProperties": "true"},
                json=build_article_number_put(version=version, article_number=probe_new),
            )
        except Exception as exc:
            step2_error = str(exc)
        art_after_narrow = client.get(f"/article/id/{test_id}")
        report["step2"] = {
            "error": step2_error,
            "number_after": art_after_narrow.get("articleNumber"),
            "ss_vs_step1": _compare(art, art_after_narrow),
            "ss_after": _ss_snapshot(art_after_narrow),
        }

        # Restore number if narrow changed it (for step 3 baseline)
        if str(art_after_narrow.get("articleNumber") or "") == probe_new:
            v = str(art_after_narrow.get("version") or "")
            client.put(
                f"/article/id/{test_id}",
                params={"ignoreMissingProperties": "true"},
                json=build_article_number_put(version=v, article_number=current_number),
            )
            art_after_narrow = client.get(f"/article/id/{test_id}")

        # Step 3: PUT with supplySources echo (fresh GET)
        art_before_wide = client.get(f"/article/id/{test_id}")
        v3 = str(art_before_wide.get("version") or "")
        wide_body: dict[str, Any] = {
            **build_article_number_put(version=v3, article_number=probe_new),
            "supplySources": art_before_wide.get("supplySources") or [],
            "primarySupplySourceId": art_before_wide.get("primarySupplySourceId"),
        }
        step3_error = None
        try:
            client.put(
                f"/article/id/{test_id}",
                params={"ignoreMissingProperties": "true"},
                json=wide_body,
            )
        except Exception as exc:
            step3_error = str(exc)
        art_after_wide = client.get(f"/article/id/{test_id}")
        report["step3"] = {
            "error": step3_error,
            "number_after": art_after_wide.get("articleNumber"),
            "ss_vs_step1": _compare(art_before_wide, art_after_wide),
            "ss_after": _ss_snapshot(art_after_wide),
        }

        # Step 4: inspect articleSupplySource records
        ss_ids = []
        for item in report["step1"].get("supplySources") or []:
            if isinstance(item, dict):
                sid = item.get("articleSupplySourceId")
                if sid:
                    ss_ids.append(str(sid))
        if report.get("created_ss_id"):
            ss_ids.append(report["created_ss_id"])
        ss_ids = list(dict.fromkeys(ss_ids))
        ss_records: list[dict[str, Any]] = []
        for sid in ss_ids:
            try:
                rec = client.get(f"/articleSupplySource/id/{sid}")
                if isinstance(rec, dict):
                    ss_records.append(
                        {
                            "id": sid,
                            "keys": sorted(rec.keys()),
                            "articleNumber": rec.get("articleNumber"),
                            "name": rec.get("name"),
                        }
                    )
            except Exception as exc:
                ss_records.append({"id": sid, "get_error": str(exc)})
        report["step4_articleSupplySource"] = ss_records

        # Cleanup: restore number, detach, delete SS
        try:
            for sid in ss_ids:
                try:
                    client.request("DELETE", f"/articleSupplySource/id/{sid}")
                    report.setdefault("cleanup_deleted_ss", []).append(sid)
                except Exception as exc:
                    report.setdefault("cleanup_errors", []).append({sid: str(exc)})
            client.request("DELETE", f"/article/id/{test_id}")
            report["cleanup_deleted_article"] = test_id
        except Exception as exc:
            report["cleanup_error"] = str(exc)

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
