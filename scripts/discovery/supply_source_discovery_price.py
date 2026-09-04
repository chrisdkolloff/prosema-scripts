"""Phase C: articleSupplySource price-write semantics and primary assignment.

ONLY 999.999.001 / SS 353019. Default dry-run; live writes need --allow-live.

    PYTHONPATH=. python scripts/discovery/supply_source_discovery_price.py
    PYTHONPATH=. python scripts/discovery/supply_source_discovery_price.py --allow-live
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
EXPECTED_ARTICLE_ID = "353023"
EXPECTED_SS_ID = "353019"
PROBE_SAN = "DISCOVERY-PROBE-PRICE"
OUT_PATH = _ROOT / "scripts" / "discovery" / "out" / "supply_source_price.md"
IGNORE_MISSING = {"ignoreMissingProperties": "true"}
VOLATILE = frozenset(
    {"version", "lastModifiedDate", "lastModifiedByUserId", "createdDate"}
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


def dump(log: list[dict[str, Any]], notes: list[str]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    chunks = ["# articleSupplySource discovery — Phase C (prices / primary)", ""]
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


def emit(notes: list[str], text: str = "") -> None:
    notes.append(text)
    print(text)


def block(notes: list[str], title: str, body: Any) -> None:
    emit(notes, f"### {title}")
    emit(notes)
    emit(notes, "```json")
    emit(notes, json.dumps(body, ensure_ascii=False, indent=2, default=str))
    emit(notes, "```")
    emit(notes)


def fetch_target(client: ProbeClient) -> dict[str, Any]:
    matches = list(client.iter_pages("article", params={"articleNumber-eq": TARGET}))
    if len(matches) != 1:
        raise SystemExit(f"Expected 1 article {TARGET!r}, got {len(matches)}")
    article = matches[0]
    number = str(article.get("articleNumber") or "")
    if number != TARGET or not number.startswith(GUARD_PREFIX):
        raise SystemExit(f"Refusing article {number!r}")
    if str(article.get("id")) != EXPECTED_ARTICLE_ID:
        raise SystemExit(
            f"Article id {article.get('id')!r} != {EXPECTED_ARTICLE_ID!r} — refusing."
        )
    return article


def get_ss(client: ProbeClient, ss_id: str) -> dict[str, Any]:
    body = client.get(f"/articleSupplySource/id/{ss_id}")
    if not isinstance(body, dict):
        raise SystemExit(f"GET SS {ss_id} returned {type(body)}")
    return body


def try_put_ss(
    client: ProbeClient, ss_id: str, payload: dict[str, Any], *, params=None
) -> tuple[str, int | None, Any]:
    try:
        body = client.put(
            f"/articleSupplySource/id/{ss_id}",
            params=IGNORE_MISSING if params is None else params,
            json=payload,
        )
        return "accepted", 200, body
    except WeclappError as exc:
        return "rejected", exc.status_code, exc.detail


def try_put_article(
    client: ProbeClient, article_id: str, payload: dict[str, Any]
) -> tuple[str, int | None, Any]:
    try:
        body = client.put(
            f"/article/id/{article_id}",
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


def strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def json_diff(a: Any, b: Any, path: str = "$") -> list[str]:
    diffs: list[str] = []
    if type(a) is not type(b) and not (
        isinstance(a, (int, float)) and isinstance(b, (int, float))
    ):
        diffs.append(f"{path}: type {type(a).__name__} vs {type(b).__name__}")
        return diffs
    if isinstance(a, dict):
        keys = set(a) | set(b)
        for k in sorted(keys):
            if k not in a:
                diffs.append(f"{path}.{k}: missing in original, now {b[k]!r}")
            elif k not in b:
                diffs.append(f"{path}.{k}: missing after restore, was {a[k]!r}")
            else:
                diffs.extend(json_diff(a[k], b[k], f"{path}.{k}"))
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: len {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(json_diff(x, y, f"{path}[{i}]"))
        return diffs
    if a != b:
        diffs.append(f"{path}: {a!r} vs {b!r}")
    return diffs


def current_price(ss: dict[str, Any]) -> dict[str, Any] | None:
    for p in ss.get("articlePrices") or []:
        if isinstance(p, dict) and p.get("endDate") is None:
            return p
    prices = [p for p in (ss.get("articlePrices") or []) if isinstance(p, dict)]
    return prices[0] if prices else None


def restore_ss_prices(
    client: ProbeClient, ss_id: str, original_ss: dict[str, Any], notes: list[str]
) -> dict[str, Any]:
    fresh = get_ss(client, ss_id)
    payload = {
        "id": fresh.get("id"),
        "version": fresh.get("version"),
        "name": original_ss.get("name"),
        "articlePrices": copy.deepcopy(original_ss.get("articlePrices") or []),
    }
    outcome, status, body = try_put_ss(client, ss_id, payload)
    block(notes, f"restore SS articlePrices ({outcome} {status})", body if outcome == "rejected" else {
        "id": (body or {}).get("id") if isinstance(body, dict) else None,
        "version": (body or {}).get("version") if isinstance(body, dict) else None,
        "n_prices": len((body or {}).get("articlePrices") or []) if isinstance(body, dict) else None,
    })
    return get_ss(client, ss_id)


def restore_article_links(
    client: ProbeClient, original_article: dict[str, Any], notes: list[str]
) -> dict[str, Any]:
    fresh = fetch_target(client)
    payload = {
        "id": fresh.get("id"),
        "version": fresh.get("version"),
        "supplySources": copy.deepcopy(original_article.get("supplySources") or []),
        "primarySupplySourceId": original_article.get("primarySupplySourceId"),
    }
    outcome, status, body = try_put_article(client, str(fresh["id"]), payload)
    block(notes, f"restore article links ({outcome} {status})", {
        "status": status,
        "detail": body if outcome == "rejected" else {
            "version": (body or {}).get("version") if isinstance(body, dict) else None,
            "primarySupplySourceId": (body or {}).get("primarySupplySourceId") if isinstance(body, dict) else None,
            "supplySources": (body or {}).get("supplySources") if isinstance(body, dict) else None,
        },
    })
    return fetch_target(client)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()

    notes: list[str] = []
    log: list[dict[str, Any]] = []
    client = ProbeClient(load_config(), allow_live=args.allow_live, log=log)
    created_ids: list[str] = []
    leftovers: list[str] = []
    restore_failed = False

    emit(notes, f"allow_live={args.allow_live} target={TARGET}")
    emit(notes, "Prompt C-A1 was truncated in chat; C-A2–C-A8 inferred from the Purpose section (replace vs merge, omit wipe, history).")
    emit(notes)

    article0 = fetch_target(client)
    ss0 = get_ss(client, EXPECTED_SS_ID)
    if str(ss0.get("id")) != EXPECTED_SS_ID:
        raise SystemExit("SS id mismatch")
    if str(article0.get("primarySupplySourceId")) not in ("", EXPECTED_SS_ID) and str(
        article0.get("primarySupplySourceId")
    ) != EXPECTED_SS_ID:
        emit(notes, f"NOTE: primarySupplySourceId is `{article0.get('primarySupplySourceId')}`")

    original_article = copy.deepcopy(article0)
    original_ss = copy.deepcopy(ss0)

    emit(notes, "## Restore-point snapshots (verbatim GET before first write)")
    emit(notes)
    block(notes, "original article", original_article)
    block(notes, "original supply source", original_ss)

    if not args.allow_live:
        emit(notes, "Dry-run: stopping before writes.")
        dump(log, notes)
        return 0

    ss_id = EXPECTED_SS_ID
    article_id = str(article0["id"])

    # ------------------------------------------------------------------ C-A1
    emit(notes, "## C-A1. Price row identity")
    emit(notes)
    prices = ss0.get("articlePrices") or []
    block(notes, "articlePrices (raw)", prices)
    emit(notes, f"- n={len(prices)}")
    for i, p in enumerate(prices):
        emit(
            notes,
            f"- row {i}: id=`{p.get('id')}` version=`{p.get('version')!r}` "
            f"price=`{p.get('price')}` startDate=`{p.get('startDate')}` "
            f"endDate=`{p.get('endDate')}` currencyId=`{p.get('currencyId')}`"
        )
    emit(notes, "- Stable key observed: nested `id` (string) on every row in this GET.")
    emit(notes)

    def ss_now() -> dict[str, Any]:
        return get_ss(client, ss_id)

    # ------------------------------------------------------------------ C-A2 omit array, ignoreMissing true
    emit(notes, "## C-A2. Omit articlePrices with ignoreMissingProperties=true")
    emit(notes)
    fresh = ss_now()
    outcome, status, body = try_put_ss(
        client,
        ss_id,
        {"id": fresh["id"], "version": fresh["version"], "name": fresh["name"]},
    )
    after = ss_now()
    block(notes, f"C-A2 PUT omit prices ({outcome} {status})", {"n_before": len(prices), "n_after": len(after.get("articlePrices") or [])})
    emit(
        notes,
        f"- prices preserved? {len(after.get('articlePrices') or []) == len(original_ss.get('articlePrices') or [])} "
        f"({len(original_ss.get('articlePrices') or [])} → {len(after.get('articlePrices') or [])})"
    )
    emit(notes, f"- version {fresh.get('version')} → {after.get('version')}")
    emit(notes)

    # ------------------------------------------------------------------ C-A3 omit without ignoreMissing
    emit(notes, "## C-A3. Omit articlePrices WITHOUT ignoreMissingProperties")
    emit(notes)
    fresh = ss_now()
    outcome, status, body = try_put_ss(
        client,
        ss_id,
        {"id": fresh["id"], "version": fresh["version"], "name": fresh["name"]},
        params={},
    )
    after = ss_now()
    block(
        notes,
        f"C-A3 PUT omit prices no-ignore ({outcome} {status})",
        body if outcome == "rejected" else {
            "n_after": len(after.get("articlePrices") or []),
            "version": after.get("version"),
        },
    )
    emit(
        notes,
        f"- n prices after: {len(after.get('articlePrices') or [])} "
        f"(wipe would be 0)"
    )
    emit(notes)

    # ------------------------------------------------------------------ C-A4 PUT only current row, changed price, keep id
    emit(notes, "## C-A4. PUT single current row with new price, keep nested id (replace vs merge)")
    emit(notes)
    fresh = ss_now()
    cur = current_price(fresh)
    if not cur:
        emit(notes, "STOP C-A4: no current price row")
    else:
        modified = copy.deepcopy(cur)
        old_price = modified.get("price")
        modified["price"] = "41.41"
        payload = {
            "id": fresh["id"],
            "version": fresh["version"],
            "name": fresh["name"],
            "articlePrices": [modified],
        }
        outcome, status, body = try_put_ss(client, ss_id, payload)
        after = ss_now()
        ids_before = [p.get("id") for p in fresh.get("articlePrices") or []]
        ids_after = [p.get("id") for p in after.get("articlePrices") or []]
        block(
            notes,
            f"C-A4 result ({outcome} {status})",
            {
                "ids_before": ids_before,
                "ids_after": ids_after,
                "prices_after": after.get("articlePrices"),
            },
        )
        emit(notes, f"- old current price `{old_price}` → sent `41.41`")
        emit(notes, f"- row count {len(ids_before)} → {len(ids_after)}")
        if len(ids_after) < len(ids_before):
            emit(notes, "- **REPLACE: omitted history rows were dropped.**")
        elif set(ids_after) == set(ids_before):
            emit(notes, "- **MERGE or rewrite-in-place: history ids still present.**")
        else:
            emit(notes, "- id set changed (new rows and/or dropped ids).")
        emit(notes)

    restore_ss_prices(client, ss_id, original_ss, notes)

    # ------------------------------------------------------------------ C-A5 new row, no nested id, single-element array
    emit(notes, "## C-A5. PUT one new price object with no nested id")
    emit(notes)
    fresh = ss_now()
    cur = current_price(fresh) or {}
    new_row = {
        "price": "42.42",
        "currencyId": cur.get("currencyId") or "261",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "startDate": 1788511200000,
    }
    outcome, status, body = try_put_ss(
        client,
        ss_id,
        {
            "id": fresh["id"],
            "version": fresh["version"],
            "name": fresh["name"],
            "articlePrices": [new_row],
        },
    )
    after = ss_now()
    block(
        notes,
        f"C-A5 result ({outcome} {status})",
        after.get("articlePrices"),
    )
    emit(notes, f"- n {len(fresh.get('articlePrices') or [])} → {len(after.get('articlePrices') or [])}")
    emit(notes)

    restore_ss_prices(client, ss_id, original_ss, notes)

    # ------------------------------------------------------------------ C-A6 empty array
    emit(notes, "## C-A6. PUT articlePrices: []")
    emit(notes)
    fresh = ss_now()
    outcome, status, body = try_put_ss(
        client,
        ss_id,
        {
            "id": fresh["id"],
            "version": fresh["version"],
            "name": fresh["name"],
            "articlePrices": [],
        },
    )
    after = ss_now()
    block(
        notes,
        f"C-A6 result ({outcome} {status})",
        after.get("articlePrices"),
    )
    emit(notes, f"- n after empty-array PUT: {len(after.get('articlePrices') or [])}")
    emit(notes)

    restore_ss_prices(client, ss_id, original_ss, notes)

    # ------------------------------------------------------------------ C-A7 history pair: old with endDate + new with startDate
    emit(notes, "## C-A7. Explicit history: keep old id with endDate + new row with startDate")
    emit(notes)
    fresh = ss_now()
    all_prices = copy.deepcopy(fresh.get("articlePrices") or [])
    cur = current_price({"articlePrices": all_prices})
    if cur:
        ended = copy.deepcopy(cur)
        ended["endDate"] = 1788511199999
        newbie = {
            "price": "43.43",
            "currencyId": cur.get("currencyId") or "261",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "startDate": 1788511200000,
        }
        others = [p for p in all_prices if p.get("id") != cur.get("id")]
        outcome, status, body = try_put_ss(
            client,
            ss_id,
            {
                "id": fresh["id"],
                "version": fresh["version"],
                "name": fresh["name"],
                "articlePrices": others + [ended, newbie],
            },
        )
        after = ss_now()
        block(notes, f"C-A7 result ({outcome} {status})", after.get("articlePrices"))
    emit(notes)

    restore_ss_prices(client, ss_id, original_ss, notes)

    # ------------------------------------------------------------------ C-A8 change currency on existing current row
    emit(notes, "## C-A8. Change currencyId on existing current price (keep id)")
    emit(notes)
    fresh = ss_now()
    cur = current_price(fresh)
    if cur:
        row = copy.deepcopy(cur)
        row["currencyId"] = "265" if str(cur.get("currencyId")) == "261" else "261"
        # send full original array with that row swapped
        arr = []
        for p in fresh.get("articlePrices") or []:
            arr.append(row if p.get("id") == cur.get("id") else copy.deepcopy(p))
        outcome, status, body = try_put_ss(
            client,
            ss_id,
            {
                "id": fresh["id"],
                "version": fresh["version"],
                "name": fresh["name"],
                "articlePrices": arr,
            },
        )
        after = ss_now()
        now_cur = current_price(after)
        block(
            notes,
            f"C-A8 result ({outcome} {status})",
            {
                "requested_currencyId": row["currencyId"],
                "current_after": now_cur,
                "n": len(after.get("articlePrices") or []),
            },
        )
    emit(notes)

    restore_ss_prices(client, ss_id, original_ss, notes)

    # ------------------------------------------------------------------ C-B primary on empty article
    emit(notes, "## C-B. Attach when article has no supply source")
    emit(notes)
    emit(notes, "No other 999.999 article exists. Temporarily unlink 999.999.001, attach a new SS, then restore.")
    emit(notes)

    fresh_a = fetch_target(client)
    outcome, status, body = try_put_article(
        client,
        article_id,
        {"id": fresh_a["id"], "version": fresh_a["version"], "supplySources": []},
    )
    empty_a = fetch_target(client)
    block(
        notes,
        f"C-B unlink all SS ({outcome} {status})",
        {
            "primarySupplySourceId": empty_a.get("primarySupplySourceId"),
            "supplySources": empty_a.get("supplySources"),
        },
    )
    emit(
        notes,
        f"- after unlink: primary=`{empty_a.get('primarySupplySourceId')}` "
        f"n_refs={len(empty_a.get('supplySources') or [])}"
    )

    created = None
    outcome, status, body = try_post(
        client,
        {
            "supplierId": original_ss.get("supplierId"),
            "articleNumber": PROBE_SAN,
            "name": "DISCOVERY-PROBE-PRICE",
            "unitId": original_ss.get("unitId"),
        },
    )
    block(notes, f"C-B POST new SS ({outcome} {status})", body)
    if outcome == "accepted" and isinstance(body, dict) and body.get("id"):
        created = str(body["id"])
        created_ids.append(created)
        empty_a = fetch_target(client)
        outcome, status, body = try_put_article(
            client,
            article_id,
            {
                "id": empty_a["id"],
                "version": empty_a["version"],
                "supplySources": [
                    {"articleSupplySourceId": created, "positionNumber": 1}
                ],
            },
        )
        linked = fetch_target(client)
        block(
            notes,
            f"C-B attach onto empty article ({outcome} {status})",
            {
                "primarySupplySourceId": linked.get("primarySupplySourceId"),
                "supplySources": linked.get("supplySources"),
            },
        )
        auto = str(linked.get("primarySupplySourceId") or "") == created
        emit(
            notes,
            f"- primary auto-set to the new SS? **{auto}** "
            f"(primary=`{linked.get('primarySupplySourceId')}` new=`{created}`)"
        )
        if not auto:
            emit(notes, "- Trying explicit primarySupplySourceId on article PUT.")
            linked = fetch_target(client)
            outcome, status, body = try_put_article(
                client,
                article_id,
                {
                    "id": linked["id"],
                    "version": linked["version"],
                    "primarySupplySourceId": created,
                    "supplySources": linked.get("supplySources") or [],
                },
            )
            linked2 = fetch_target(client)
            block(
                notes,
                f"C-B explicit primary ({outcome} {status})",
                {
                    "primarySupplySourceId": linked2.get("primarySupplySourceId"),
                    "supplySources": linked2.get("supplySources"),
                },
            )
        emit(notes)

    # ------------------------------------------------------------------ final restore
    emit(notes, "## Final restore")
    emit(notes)
    art_restored = restore_article_links(client, original_article, notes)
    ss_restored = restore_ss_prices(client, ss_id, original_ss, notes)

    for cid in list(created_ids):
        outcome, status, body = try_delete(client, cid)
        block(notes, f"DELETE probe SS {cid} ({outcome} {status})", body)
        if outcome != "accepted":
            leftovers.append(cid)
        else:
            created_ids.remove(cid)

    art_final = fetch_target(client)
    ss_final = get_ss(client, ss_id)

    emit(notes, "## Restore diff vs original GET (full keys)")
    emit(notes)
    d_art = json_diff(original_article, art_final)
    d_ss = json_diff(original_ss, ss_final)
    emit(notes, f"- article full-diff lines: {len(d_art)}")
    for line in d_art[:80]:
        emit(notes, f"  - {line}")
    emit(notes, f"- SS full-diff lines: {len(d_ss)}")
    for line in d_ss[:80]:
        emit(notes, f"  - {line}")
    emit(notes)
    emit(notes, "## Restore diff ignoring version/lastModifiedDate/createdDate/lastModifiedByUserId")
    emit(notes)
    d_art_s = json_diff(strip_volatile(original_article), strip_volatile(art_final))
    d_ss_s = json_diff(strip_volatile(original_ss), strip_volatile(ss_final))
    if d_art_s:
        restore_failed = True
        emit(notes, "ARTICLE SEMANTIC DIFF (restore incomplete):")
        for line in d_art_s:
            emit(notes, f"  - {line}")
    else:
        emit(notes, "- article semantic restore: **match**")
    if d_ss_s:
        restore_failed = True
        emit(notes, "SS SEMANTIC DIFF (restore incomplete):")
        for line in d_ss_s:
            emit(notes, f"  - {line}")
    else:
        emit(notes, "- supply-source semantic restore: **match**")
    emit(notes)

    if leftovers:
        restore_failed = True
        emit(notes, "CLEANUP FAILED leftover SS ids: " + ", ".join(leftovers))
    if restore_failed:
        emit(notes, "**RESTORE FAILED — inspect leftovers and diffs above.**")
    else:
        emit(notes, "Restore: original prices and article links match ignoring version/timestamps.")

    dump(log, notes)
    return 1 if restore_failed or leftovers else 0


if __name__ == "__main__":
    raise SystemExit(main())
