"""Phase B write probes for weclapp articleSupplySource.

Default is dry-run. Live writes require --allow-live.

ONLY article 999.999.001. Never creates a test article. Never touches other numbers.

    PYTHONPATH=. python scripts/discovery/supply_source_discovery_write.py
    PYTHONPATH=. python scripts/discovery/supply_source_discovery_write.py --allow-live
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.weclapp.client import WeclappClient, WeclappError
from scripts.weclapp.config import load_config

TARGET = "999.999.001"
GUARD_PREFIX = "999.999"
MARKER = "__SS_PROBE__"
PROBE_SAN = "DISCOVERY-PROBE-DO-NOT-USE"
OUT_PATH = _ROOT / "scripts" / "discovery" / "out" / "supply_source_write.md"
IGNORE_MISSING = {"ignoreMissingProperties": "true"}

# Fields from Phase A GET that we test one-at-a-time on top of a known-good PUT.
B1_FIELDS = (
    "id",
    "createdDate",
    "lastModifiedDate",
    "customAttributes",
    "dropshippingPossible",
    "ean",
    "ignoreInDropshippingAutomation",
    "matchCode",
    "articleNumber",
    "supplierId",
    "taxRateType",
    "unitId",
    "articlePrices",
    "description",
    "fixedPurchaseQuantity",
    "minimumPurchaseQuantity",
    "procurementLeadDays",
    "shortDescription1",
)


def _compat_base_url(tenant: str) -> str:
    tenant = tenant.strip()
    suffix = ".weclapp.com"
    if tenant.endswith(suffix):
        tenant = tenant[: -len(suffix)]
    return "https://{}.weclapp.com/webapp/api/v2".format(tenant)


class ProbeClient(WeclappClient):
    def __init__(self, config, *, allow_live: bool, log: list[dict[str, Any]]) -> None:
        super().__init__(config)
        self.allow_live = allow_live
        self.log = log

    @property
    def base_url(self) -> str:
        return _compat_base_url(self.config.tenant)

    def request(self, method, path, *, params=None, json=None):
        if method.upper() != "GET" and not self.allow_live:
            self.log.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "method": method,
                    "path": path,
                    "params": params,
                    "request_body": json,
                    "status": None,
                    "response_body": "DRY-RUN: not sent",
                    "skipped": True,
                }
            )
            return None
        try:
            body = super().request(method, path, params=params, json=json)
            self.log.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "method": method,
                    "path": path,
                    "params": params,
                    "request_body": json,
                    "status": 200,
                    "response_body": body,
                    "skipped": False,
                }
            )
            return body
        except WeclappError as exc:
            self.log.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "method": method,
                    "path": path,
                    "params": params,
                    "request_body": json,
                    "status": exc.status_code,
                    "response_body": exc.detail,
                    "skipped": False,
                }
            )
            raise


def dump_log(log: list[dict[str, Any]], notes: list[str]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    chunks = ["# articleSupplySource discovery — Phase B", ""]
    chunks.extend(notes)
    chunks.append("")
    chunks.append("## Request / response log")
    chunks.append("")
    for i, entry in enumerate(log, 1):
        chunks.append(
            f"### {i}. {entry['method']} {entry['path']} status={entry.get('status')}"
        )
        chunks.append("")
        chunks.append("```json")
        chunks.append(json.dumps(entry, ensure_ascii=False, indent=2, default=str))
        chunks.append("```")
        chunks.append("")
    OUT_PATH.write_text("\n".join(chunks) + "\n", encoding="utf-8")


def fetch_target(client: ProbeClient) -> dict[str, Any]:
    matches = list(client.iter_pages("article", params={"articleNumber-eq": TARGET}))
    if len(matches) != 1:
        raise SystemExit(f"Expected 1 article {TARGET!r}, got {len(matches)}")
    article = matches[0]
    number = str(article.get("articleNumber") or "")
    if number != TARGET or not number.startswith(GUARD_PREFIX):
        raise SystemExit(f"Refusing article {number!r}")
    return article


def ss_ids_from_article(article: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    primary = str(article.get("primarySupplySourceId") or "").strip()
    if primary:
        ids.append(primary)
    for ref in article.get("supplySources") or []:
        if not isinstance(ref, dict):
            continue
        sid = str(ref.get("articleSupplySourceId") or "").strip()
        if sid and sid not in ids:
            ids.append(sid)
    return ids


def get_ss(client: ProbeClient, ss_id: str) -> dict[str, Any]:
    body = client.get(f"/articleSupplySource/id/{ss_id}")
    if not isinstance(body, dict):
        raise SystemExit(f"GET SS {ss_id} returned {type(body)}")
    return body


def try_put(
    client: ProbeClient, ss_id: str, payload: dict[str, Any]
) -> tuple[str, int | None, Any]:
    try:
        body = client.put(
            f"/articleSupplySource/id/{ss_id}",
            params=IGNORE_MISSING,
            json=payload,
        )
        return "accepted", 200, body
    except WeclappError as exc:
        return "rejected", exc.status_code, exc.detail


def try_post(client: ProbeClient, payload: dict[str, Any]) -> tuple[str, int | None, Any]:
    try:
        body = client.post("/articleSupplySource", json=payload)
        return "accepted", 200, body
    except WeclappError as exc:
        return "rejected", exc.status_code, exc.detail


def try_delete(client: ProbeClient, ss_id: str) -> tuple[str, int | None, Any]:
    try:
        body = client.request("DELETE", f"/articleSupplySource/id/{ss_id}")
        return "accepted", 200, body
    except WeclappError as exc:
        return "rejected", exc.status_code, exc.detail


def note_result(notes: list[str], label: str, outcome: str, status: int | None, body: Any) -> None:
    notes.append(f"### {label}")
    notes.append("")
    notes.append(f"- outcome: **{outcome}** status `{status}`")
    notes.append("```json")
    notes.append(json.dumps(body, ensure_ascii=False, indent=2, default=str)[:8000])
    notes.append("```")
    notes.append("")


def current_price(ss: dict[str, Any]) -> dict[str, Any] | None:
    for p in ss.get("articlePrices") or []:
        if isinstance(p, dict) and p.get("endDate") is None:
            return p
    prices = ss.get("articlePrices") or []
    return prices[0] if prices and isinstance(prices[0], dict) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()

    notes: list[str] = [
        f"allow_live={args.allow_live}",
        f"target={TARGET}",
        "PUT uses ignoreMissingProperties=true (same query param as article write path).",
    ]
    log: list[dict[str, Any]] = []
    client = ProbeClient(load_config(), allow_live=args.allow_live, log=log)
    created_ids: list[str] = []
    leftovers: list[str] = []
    original_ss: dict[str, Any] | None = None

    try:
        article = fetch_target(client)
        notes.append(f"article id=`{article.get('id')}` version=`{article.get('version')}`")
        ids = ss_ids_from_article(article)
        notes.append(f"supply source ids on article: {ids}")
        if not ids:
            notes.append(
                "STOP: 999.999.001 has no supply source. Not creating one as a PUT "
                "baseline. B3 create still attempted below if --allow-live."
            )
            baseline = None
        else:
            baseline = get_ss(client, ids[0])
            original_ss = copy.deepcopy(baseline)
            notes.append(
                f"baseline SS id=`{baseline.get('id')}` version=`{baseline.get('version')!r}` "
                f"SAN=`{baseline.get('articleNumber')}` name=`{baseline.get('name')}` "
                f"supplierId=`{baseline.get('supplierId')}`"
            )

        if not args.allow_live:
            notes.append("Dry-run: not sending writes.")
            dump_log(log, notes)
            print("\n".join(notes))
            return 0

        ss_id = str(baseline["id"]) if baseline else ""

        # ------------------------------------------------------------------ B4 + known-good
        known_good: dict[str, Any] | None = None
        if baseline:
            candidates = [
                {
                    "id": baseline.get("id"),
                    "version": baseline.get("version"),
                    "name": baseline.get("name"),
                },
                {
                    "id": baseline.get("id"),
                    "version": baseline.get("version"),
                    "name": baseline.get("name"),
                    "articleNumber": baseline.get("articleNumber"),
                    "supplierId": baseline.get("supplierId"),
                    "unitId": baseline.get("unitId"),
                    "taxRateType": baseline.get("taxRateType"),
                },
            ]
            notes.append("## Known-good PUT (also B4 no-op if values unchanged)")
            notes.append("")
            before = get_ss(client, ss_id)
            v_before = before.get("version")
            lm_before = before.get("lastModifiedDate")
            for i, payload in enumerate(candidates, 1):
                outcome, status, body = try_put(client, ss_id, payload)
                note_result(notes, f"known-good candidate {i}", outcome, status, body)
                if outcome == "accepted":
                    known_good = payload
                    after = get_ss(client, ss_id)
                    notes.append(
                        f"- after no-op-ish PUT: version `{v_before}` → `{after.get('version')}` "
                        f"lastModifiedDate `{lm_before}` → `{after.get('lastModifiedDate')}` "
                        f"name unchanged={after.get('name') == before.get('name')}"
                    )
                    notes.append(
                        "- B4 Dennis UI audit: **unknown** (not observable via this API)."
                    )
                    notes.append("")
                    if after.get("version") != v_before:
                        notes.append(
                            "- **No-op PUT bumped version** (or lastModifiedDate changed)."
                        )
                        notes.append("")
                    known_good["version"] = after.get("version")
                    break
            if known_good is None:
                notes.append("STOP: no known-good PUT established. Skipping B1/B2.")
                notes.append("")

        # ------------------------------------------------------------------ B2
        if baseline and known_good:
            notes.append("## B2 Optimistic locking")
            notes.append("")
            fresh = get_ss(client, ss_id)
            v = fresh.get("version")

            payload = dict(known_good)
            payload["version"] = v
            outcome, status, body = try_put(client, ss_id, payload)
            note_result(notes, "B2a correct version", outcome, status, body)
            after = get_ss(client, ss_id)
            notes.append(f"- version now `{after.get('version')}`")
            notes.append("")

            stale = dict(known_good)
            stale["version"] = "0" if str(v) != "0" else "1"
            stale["name"] = (str(fresh.get("name") or "") + " " + MARKER)[:80]
            outcome, status, body = try_put(client, ss_id, stale)
            note_result(notes, "B2b stale version", outcome, status, body)
            after_stale = get_ss(client, ss_id)
            notes.append(
                f"- name after stale PUT: `{after_stale.get('name')}` "
                f"(changed={after_stale.get('name') != after.get('name')})"
            )
            notes.append("")

            omitted = dict(known_good)
            omitted.pop("version", None)
            omitted["name"] = (str(after_stale.get("name") or "") + " NOV")[:80]
            outcome, status, body = try_put(client, ss_id, omitted)
            note_result(notes, "B2c version omitted", outcome, status, body)
            after_om = get_ss(client, ss_id)
            notes.append(
                f"- name after omit-version PUT: `{after_om.get('name')}` "
                f"(changed={after_om.get('name') != after_stale.get('name')})"
            )
            if outcome == "accepted":
                notes.append(
                    "- **DANGER: PUT succeeded with version omitted.** Same class of bug "
                    "as the article path before we made version mandatory."
                )
            notes.append("")

            # restore name
            rest = get_ss(client, ss_id)
            restore = {
                "id": rest.get("id"),
                "version": rest.get("version"),
                "name": original_ss.get("name") if original_ss else rest.get("name"),
            }
            try_put(client, ss_id, restore)

        # ------------------------------------------------------------------ B1
        if baseline and known_good:
            notes.append("## B1 Read-only fields (one extra field vs known-good)")
            notes.append("")
            readonly: list[str] = []
            writable_or_ignored: list[str] = []
            for field in B1_FIELDS:
                fresh = get_ss(client, ss_id)
                if field not in fresh and field not in ("description", "ean", "matchCode"):
                    notes.append(f"- skip `{field}`: not on GET of this SS")
                    continue
                payload = {
                    "id": fresh.get("id"),
                    "version": fresh.get("version"),
                    "name": fresh.get("name"),
                }
                if field in fresh:
                    payload[field] = copy.deepcopy(fresh[field])
                else:
                    continue
                outcome, status, body = try_put(client, ss_id, payload)
                note_result(notes, f"B1 field `{field}`", outcome, status, body)
                if outcome == "rejected":
                    readonly.append(field)
                else:
                    writable_or_ignored.append(field)

            notes.append(
                f"Rejected (read-only or invalid when included): {readonly or '(none)'}"
            )
            notes.append(
                f"Accepted: {writable_or_ignored or '(none)'}"
            )
            notes.append("")

            # poison: valid name change + createdDate (or first rejected field)
            poison_field = "createdDate" if "createdDate" in readonly else (
                readonly[0] if readonly else None
            )
            notes.append("## B1b poison: valid name change + one rejected field")
            notes.append("")
            if poison_field is None:
                notes.append("No rejected field to poison with.")
                notes.append("")
            else:
                fresh = get_ss(client, ss_id)
                new_name = (str(original_ss.get("name") if original_ss else "") + " " + MARKER)[:80]
                payload = {
                    "id": fresh.get("id"),
                    "version": fresh.get("version"),
                    "name": new_name,
                    poison_field: copy.deepcopy(fresh.get(poison_field)),
                }
                outcome, status, body = try_put(client, ss_id, payload)
                note_result(
                    notes,
                    f"poison name+`{poison_field}`",
                    outcome,
                    status,
                    body,
                )
                after = get_ss(client, ss_id)
                notes.append(
                    f"- name applied? `{after.get('name')}` == intended `{new_name}` → "
                    f"{after.get('name') == new_name}"
                )
                if outcome == "rejected" and after.get("name") != new_name:
                    notes.append(
                        "- **Valid change was discarded** (same as article endpoint)."
                    )
                elif after.get("name") == new_name:
                    notes.append(
                        "- Valid change was applied despite the extra field "
                        "(unlike article endpoint)."
                    )
                notes.append("")
                rest = get_ss(client, ss_id)
                try_put(
                    client,
                    ss_id,
                    {
                        "id": rest.get("id"),
                        "version": rest.get("version"),
                        "name": original_ss.get("name") if original_ss else rest.get("name"),
                    },
                )

        # ------------------------------------------------------------------ B3 / B5 create
        notes.append("## B3 Minimal create")
        notes.append("")
        supplier_id = (baseline or {}).get("supplierId") or (original_ss or {}).get("supplierId")
        unit_id = (baseline or {}).get("unitId")
        tax = (baseline or {}).get("taxRateType") or "STANDARD"
        party = None
        party_currency = None
        if supplier_id:
            try:
                party = client.get(f"/party/id/{supplier_id}")
                party_currency = party.get("currencyId") if isinstance(party, dict) else None
            except WeclappError as exc:
                notes.append(f"party GET failed: {exc.status_code} {exc.detail}")
        cur_price = current_price(baseline) if baseline else None
        ss_currency = cur_price.get("currencyId") if cur_price else None
        other_currency = "265" if str(ss_currency) == "261" else "261"

        full_create = {
            "articleId": article.get("id"),
            "supplierId": supplier_id,
            "articleNumber": PROBE_SAN,
            "name": "DISCOVERY-PROBE",
            "unitId": unit_id,
            "taxRateType": tax,
            "dropshippingPossible": False,
            "ignoreInDropshippingAutomation": True,
            "articlePrices": [
                {
                    "price": "1.00",
                    "currencyId": ss_currency or party_currency or "261",
                    "priceScaleType": "SCALE_FROM",
                    "priceScaleValue": "0",
                }
            ],
        }
        notes.append("Starting create payload:")
        notes.append("```json")
        notes.append(json.dumps(full_create, ensure_ascii=False, indent=2, default=str))
        notes.append("```")
        notes.append("")

        outcome, status, body = try_post(client, full_create)
        note_result(notes, "B3 full create", outcome, status, body)
        if outcome == "accepted" and isinstance(body, dict) and body.get("id"):
            created_ids.append(str(body["id"]))
            # shrink: drop optional-looking keys one group at a time on NEW creates
            shrink_order = [
                ["dropshippingPossible", "ignoreInDropshippingAutomation"],
                ["articlePrices"],
                ["taxRateType"],
                ["unitId"],
                ["name"],
                ["articleNumber"],
                ["articleId"],
            ]
            required_guess = [
                "articleId",
                "supplierId",
                "articleNumber",
                "name",
                "unitId",
                "taxRateType",
                "articlePrices",
            ]
            notes.append(
                "Shrink: after a success, DELETE then retry without the next group."
            )
            notes.append("")
            current = copy.deepcopy(full_create)
            for group in shrink_order:
                # delete last created
                last = created_ids[-1]
                d_out, d_st, d_body = try_delete(client, last)
                note_result(notes, f"cleanup before shrink {group}", d_out, d_st, d_body)
                if d_out == "accepted":
                    created_ids.remove(last)
                else:
                    leftovers.append(last)
                    break
                trial = copy.deepcopy(current)
                for k in group:
                    trial.pop(k, None)
                outcome, status, body = try_post(client, trial)
                note_result(notes, f"B3 without {group}", outcome, status, body)
                if outcome == "accepted" and isinstance(body, dict) and body.get("id"):
                    created_ids.append(str(body["id"]))
                    current = trial
                    for k in group:
                        if k in required_guess:
                            required_guess.remove(k)
                else:
                    notes.append(f"- `{group}` appears required (or create failed for another reason).")
                    notes.append("")
                    # recreate full remaining current so later shrinks still have a row? skip
                    outcome2, status2, body2 = try_post(client, current)
                    note_result(notes, "re-POST last-good after failed shrink", outcome2, status2, body2)
                    if outcome2 == "accepted" and isinstance(body2, dict) and body2.get("id"):
                        created_ids.append(str(body2["id"]))
            notes.append(f"Fields still in last-good create (not proven minimal): {sorted(current)}")
            notes.append(f"Removed successfully during shrink: see log. Working set keys: {sorted(current.keys())}")
            notes.append("")

        # B5 mismatch currency on create
        notes.append("## B5 Currency on create")
        notes.append("")
        notes.append(
            f"party currencyId=`{party_currency}` SS current price currencyId=`{ss_currency}` "
            f"mismatch candidate=`{other_currency}`"
        )
        mismatch = copy.deepcopy(full_create)
        mismatch["articleNumber"] = PROBE_SAN + "-CHF"
        mismatch["articlePrices"] = [
            {
                "price": "1.00",
                "currencyId": other_currency,
                "priceScaleType": "SCALE_FROM",
                "priceScaleValue": "0",
            }
        ]
        outcome, status, body = try_post(client, mismatch)
        note_result(notes, "B5 create with mismatched currencyId", outcome, status, body)
        if outcome == "accepted" and isinstance(body, dict) and body.get("id"):
            created_ids.append(str(body["id"]))
            got = None
            prices = body.get("articlePrices") or []
            if prices:
                got = prices[0].get("currencyId")
            notes.append(f"- created currencyId on first price: `{got}` (requested `{other_currency}`)")
            notes.append("")

        notes.append(
            "Template gap (inference vs today's CSV columns, not a live POST of the "
            "CSV): create likely needs articleId (PROSEMA article) which the CSV "
            "expresses as W; supplierId from F; SAN as D/articleNumber; unitId from O; "
            "prices from G+N+R. V is still unknown as an API field."
        )
        notes.append("")

    finally:
        for ss_id in list(created_ids):
            outcome, status, body = try_delete(client, ss_id)
            note_result(notes, f"final DELETE {ss_id}", outcome, status, body)
            if outcome != "accepted":
                leftovers.append(ss_id)
            else:
                created_ids.remove(ss_id)
        if original_ss and args.allow_live:
            try:
                rest = get_ss(client, str(original_ss["id"]))
                if rest.get("name") != original_ss.get("name"):
                    try_put(
                        client,
                        str(original_ss["id"]),
                        {
                            "id": rest.get("id"),
                            "version": rest.get("version"),
                            "name": original_ss.get("name"),
                        },
                    )
            except (WeclappError, SystemExit):
                leftovers.append("restore original SS name failed")
        if leftovers:
            notes.append("CLEANUP FAILED — leftover: " + ", ".join(leftovers))
        else:
            notes.append("Cleanup: no leftovers reported.")
        dump_log(log, notes)

    print("\n".join(notes))
    print(f"Wrote {OUT_PATH}", file=sys.stderr)
    return 0 if not leftovers else 1


if __name__ == "__main__":
    raise SystemExit(main())
