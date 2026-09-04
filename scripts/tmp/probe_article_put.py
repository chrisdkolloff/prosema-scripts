"""Probe weclapp PUT /article semantics before designing the write-back path.

Answers eight questions that the bulk-transform design branches on:

  P2  Does a partial PUT with the correct version succeed, and does version increment?
  P3  Does a PUT with a STALE version get rejected?          <-- the important one
  P4  Is version optional? What happens if it is omitted entirely?
  P5  Does version increment on a no-op PUT (same values)?
  P6  What happens to a read-only field (lowLevelCode) sent alone?
  P7  Does one read-only field poison an otherwise valid payload?
  P8  Does a partial customAttributes array MERGE or WIPE the other attributes?

Runs read-only unless --apply is given. Refuses to touch anything whose article
number does not start with 999.999.

    PYTHONPATH=. python scripts/tmp/probe_article_put.py
    PYTHONPATH=. python scripts/tmp/probe_article_put.py --apply

Restores every field it touched at the end. Verify manually afterwards anyway.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.weclapp.client import WeclappClient
from scripts.weclapp.config import load_config

TARGET = "999.999.001"
GUARD_PREFIX = "999.999"
MARKER = "__PROBE__"
IGNORE_MISSING = {"ignoreMissingProperties": "true"}

results: list[dict[str, Any]] = []


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def fetch(client: WeclappClient, number: str) -> dict:
    """Fetch the target article by number. weclapp v2 filter syntax."""
    matches = list(
        client.iter_pages("article", params={"articleNumber-eq": number})
    )
    if not matches:
        raise SystemExit(f"Article {number!r} not found in this tenant.")
    if len(matches) > 1:
        raise SystemExit(f"{len(matches)} articles match {number!r} — refusing.")
    return matches[0]


def describe_error(exc: Exception) -> dict[str, Any]:
    """Pull status code and body out of whatever the client raises."""
    response = getattr(exc, "response", None)
    if response is not None:
        body = getattr(response, "text", "")
        return {
            "raised": True,
            "status": getattr(response, "status_code", None),
            "body": body[:1200],
        }
    return {"raised": True, "status": None, "body": repr(exc)[:1200]}


def probe(
    client: WeclappClient,
    label: str,
    question: str,
    article_id: str,
    payload: dict,
    *,
    apply: bool,
    params: dict | None = None,
) -> dict[str, Any]:
    """Run one PUT and record what happened. Never raises."""
    entry: dict[str, Any] = {
        "probe": label,
        "question": question,
        "payload_keys": sorted(payload.keys()),
        "version_sent": payload.get("version", "<omitted>"),
    }
    print(f"\n=== {label} — {question}")
    print(f"    payload keys : {entry['payload_keys']}")
    print(f"    version sent : {entry['version_sent']}")

    if not apply:
        entry["result"] = "skipped (dry run)"
        print("    SKIPPED (dry run)")
        results.append(entry)
        return entry

    try:
        response = client.put(
            f"/article/id/{article_id}",
            params=params if params is not None else IGNORE_MISSING,
            json=payload,
        )
        entry["raised"] = False
        entry["result"] = "accepted"
        # The client may or may not return parsed JSON; tolerate both.
        if isinstance(response, dict):
            entry["returned_version"] = response.get("version")
        print("    ACCEPTED")
    except Exception as exc:  # noqa: BLE001 - we want everything here
        entry.update(describe_error(exc))
        entry["result"] = "rejected"
        print(f"    REJECTED  status={entry.get('status')}")
        print(f"    body: {entry.get('body', '')[:400]}")

        results.append(entry)
        return entry

    results.append(entry)
    return entry


def observe(client: WeclappClient, article_id: str, note: str) -> dict:
    """GET the article and print the fields we care about."""
    fresh = list(client.iter_pages("article", params={"articleNumber-eq": TARGET}))[0]
    attrs = fresh.get("customAttributes") or []
    print(f"    -> after {note}:")
    print(f"       version            = {fresh.get('version')}")
    print(f"       name               = {fresh.get('name')!r}")
    print(f"       shortDescription1  = {str(fresh.get('shortDescription1'))[:60]!r}")
    print(f"       lowLevelCode       = {fresh.get('lowLevelCode')!r}")
    print(f"       customAttributes   = {len(attrs)} entries")
    return fresh


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually send PUTs")
    parser.add_argument("--article", default=TARGET, help="test article number")
    parser.add_argument(
        "--out",
        default="probe_article_put_results.json",
        help="where to write the machine-readable results",
    )
    args = parser.parse_args()

    if not args.article.startswith(GUARD_PREFIX):
        raise SystemExit(
            f"Refusing to probe {args.article!r}: only {GUARD_PREFIX}.* is allowed."
        )

    client = WeclappClient(load_config())

    # ---- P1: baseline ----------------------------------------------------
    print(f"=== P1 — baseline for {args.article}")
    base = fetch(client, args.article)
    article_id = str(base["id"])
    v0 = base.get("version")
    baseline = {
        "name": base.get("name"),
        "longText": base.get("longText"),
        "shortDescription1": base.get("shortDescription1"),
        "lowLevelCode": base.get("lowLevelCode"),
        "customAttributes": copy.deepcopy(base.get("customAttributes") or []),
    }
    print(f"    id      = {article_id}")
    print(f"    version = {v0!r}  (type {type(v0).__name__})")
    print(f"    name    = {baseline['name']!r}")
    print(f"    attrs   = {len(baseline['customAttributes'])} entries")
    print(f"    lowLevelCode = {baseline['lowLevelCode']!r}")
    results.append({"probe": "P1", "baseline_version": v0, "article_id": article_id})

    if not args.apply:
        print("\nDry run. Re-run with --apply to execute the probes.")
        return 0

    # ---- P2: happy path --------------------------------------------------
    probe(
        client, "P2", "partial PUT with correct version",
        article_id,
        {"name": f"{baseline['name']} {MARKER}", "version": v0},
        apply=True,
    )
    after_p2 = observe(client, article_id, "P2")
    v1 = after_p2.get("version")
    results.append({"probe": "P2-observed", "version_after": v1, "incremented": v1 != v0})

    # ---- P3: stale version ----------------------------------------------
    probe(
        client, "P3", "PUT with STALE version (v0, now superseded)",
        article_id,
        {"name": f"{baseline['name']} {MARKER} stale", "version": v0},
        apply=True,
    )
    after_p3 = observe(client, article_id, "P3")
    results.append(
        {
            "probe": "P3-observed",
            "name_changed": after_p3.get("name") != after_p2.get("name"),
            "version_after": after_p3.get("version"),
        }
    )
    v_cur = after_p3.get("version")

    # ---- P4: version omitted --------------------------------------------
    probe(
        client, "P4", "PUT with NO version key at all",
        article_id,
        {"name": f"{baseline['name']} {MARKER} noversion"},
        apply=True,
    )
    after_p4 = observe(client, article_id, "P4")
    results.append(
        {
            "probe": "P4-observed",
            "name_changed": after_p4.get("name") != after_p3.get("name"),
            "version_after": after_p4.get("version"),
        }
    )
    v_cur = after_p4.get("version")

    # ---- P5: no-op PUT ---------------------------------------------------
    probe(
        client, "P5", "PUT with identical values (no-op)",
        article_id,
        {"name": after_p4.get("name"), "version": v_cur},
        apply=True,
    )
    after_p5 = observe(client, article_id, "P5")
    results.append(
        {
            "probe": "P5-observed",
            "version_before": v_cur,
            "version_after": after_p5.get("version"),
            "bumped_on_noop": after_p5.get("version") != v_cur,
        }
    )
    v_cur = after_p5.get("version")

    # ---- P6: read-only field alone --------------------------------------
    probe(
        client, "P6", "PUT lowLevelCode alone (known read-only)",
        article_id,
        {"lowLevelCode": 99, "version": v_cur},
        apply=True,
    )
    after_p6 = observe(client, article_id, "P6")
    results.append(
        {
            "probe": "P6-observed",
            "lowLevelCode_changed": after_p6.get("lowLevelCode") != baseline["lowLevelCode"],
            "version_after": after_p6.get("version"),
        }
    )
    v_cur = after_p6.get("version")

    # ---- P7: read-only mixed with a valid field -------------------------
    poison_value = f"{MARKER} poison-test"
    probe(
        client, "P7", "PUT valid shortDescription1 + read-only lowLevelCode",
        article_id,
        {"shortDescription1": poison_value, "lowLevelCode": 99, "version": v_cur},
        apply=True,
    )
    after_p7 = observe(client, article_id, "P7")
    results.append(
        {
            "probe": "P7-observed",
            "valid_field_landed": after_p7.get("shortDescription1") == poison_value,
            "version_after": after_p7.get("version"),
        }
    )
    v_cur = after_p7.get("version")

    # ---- P8: partial customAttributes array ------------------------------
    attrs = after_p7.get("customAttributes") or []
    string_attrs = [
        a for a in attrs
        if isinstance(a, dict) and isinstance(a.get("stringValue"), str)
    ]
    if not string_attrs:
        print("\n=== P8 — SKIPPED: no string custom attribute on this article.")
        print("    Add one in weclapp (e.g. Grundmaterial) and re-run for P8.")
        results.append({"probe": "P8", "result": "skipped — no string attr present"})
    else:
        single = copy.deepcopy(string_attrs[0])
        original_attr_count = len(attrs)
        single["stringValue"] = f"{MARKER}-attr"
        probe(
            client, "P8",
            f"PUT customAttributes with ONE of {original_attr_count} entries",
            article_id,
            {"customAttributes": [single], "version": v_cur},
            apply=True,
        )
        after_p8 = observe(client, article_id, "P8")
        new_attrs = after_p8.get("customAttributes") or []
        results.append(
            {
                "probe": "P8-observed",
                "attrs_before": original_attr_count,
                "attrs_after": len(new_attrs),
                "behaviour": (
                    "merge" if len(new_attrs) == original_attr_count
                    else "wipe" if len(new_attrs) == 1
                    else "unclear"
                ),
                "version_after": after_p8.get("version"),
            }
        )
        v_cur = after_p8.get("version")

    # ---- restore ---------------------------------------------------------
    print("\n=== RESTORE — putting every touched field back")
    restore = {
        "name": baseline["name"],
        "longText": baseline["longText"],
        "shortDescription1": baseline["shortDescription1"],
        "customAttributes": baseline["customAttributes"],
        "version": v_cur,
    }
    try:
        client.put(
            f"/article/id/{article_id}", params=IGNORE_MISSING, json=restore
        )
        print("    restore PUT accepted")
    except Exception as exc:  # noqa: BLE001
        print(f"    RESTORE FAILED: {describe_error(exc)}")
        print("    !! Fix 999.999.001 by hand in weclapp before doing anything else.")

    final = observe(client, article_id, "RESTORE")
    clean = MARKER not in json.dumps(final, ensure_ascii=False, default=str)
    print(f"\n    marker {MARKER} still present anywhere: {not clean}")
    results.append({"probe": "restore", "clean": clean})

    out = Path(args.out)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
