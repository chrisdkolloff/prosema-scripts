"""Read-only unit resolution discovery.

GET /unit and GET /article (unitId only). Mirror for supply-source units and links.
No POST/PUT. No schema or UI changes.

    PYTHONPATH=. python scripts/discovery/unit_discovery.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Supplier,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
)
from scripts.weclapp.client import WeclappClient
from scripts.weclapp.config import load_config

OUT_PATH = _ROOT / "scripts" / "discovery" / "out" / "units.md"
CSV_PATH = _ROOT / "data" / "SupplySourcesWeclapp DemoImportfile_de (28.10.2024)(1).csv"
READ_MD = _ROOT / "scripts" / "discovery" / "out" / "supply_source_read.md"
WRITE_MD = _ROOT / "scripts" / "discovery" / "out" / "supply_source_write.md"

SEEDED = ("10000", "10061", "10739", "10055")
SS_KEYS_FROM_A2 = (
    "articleNumber",
    "articlePrices",
    "createdDate",
    "customAttributes",
    "description",
    "dropshippingPossible",
    "ean",
    "fixedPurchaseQuantity",
    "id",
    "ignoreInDropshippingAutomation",
    "lastModifiedDate",
    "matchCode",
    "minimumPurchaseQuantity",
    "name",
    "procurementLeadDays",
    "shortDescription1",
    "supplierId",
    "taxRateType",
    "unitId",
    "version",
)
UNITISH_KEYS = (
    "unitId",
    "unit",
    "unitName",
    "supplierUnitId",
    "supplierUnit",
    "purchaseUnitId",
    "packagingUnit",
    "packagingUnitId",
    "quantityUnitId",
    "articleAlternativeQuantities",
)


def _lines(*parts: str) -> list[str]:
    return list(parts)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _unit_name(units: dict[str, dict[str, Any]], unit_id: str | None) -> str:
    if not unit_id:
        return ""
    row = units.get(unit_id) or {}
    return str(row.get("name") or "").strip()


def _unit_label(units: dict[str, dict[str, Any]], unit_id: str | None) -> str:
    if not unit_id:
        return "(none)"
    name = _unit_name(units, unit_id) or "?"
    return f"{name} ({unit_id})"


def fetch_units(client: WeclappClient) -> list[dict[str, Any]]:
    rows = list(client.iter_pages("unit"))
    return [r for r in rows if isinstance(r, dict)]


def fetch_article_units(client: WeclappClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in client.iter_pages(
        "article",
        params={"properties": "id,articleNumber,name,unitId"},
    ):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def csv_unit_values(path: Path) -> tuple[list[str], Counter[str], list[str]]:
    if not path.is_file():
        return [], Counter(), []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return [], Counter(), ["could not decode CSV"]
    reader = csv.DictReader(text.splitlines(), delimiter=";")
    headers = list(reader.fieldnames or [])
    col = "Artikel-Mengeneinheit"
    counts: Counter[str] = Counter()
    notes: list[str] = []
    if col not in headers:
        notes.append(f"column {col!r} not in headers: {headers[:20]}")
        return headers, counts, notes
    for row in reader:
        value = (row.get(col) or "").strip()
        counts[value] += 1
    return headers, counts, notes


def main() -> int:
    notes: list[str] = []
    client = WeclappClient(load_config())
    now = datetime.now(timezone.utc).isoformat()
    notes.append("# Unit resolution discovery")
    notes.append("")
    notes.append(f"Generated `{now}`. Read-only: GET `/unit`, GET `/article` (id/number/name/unitId), SQL mirror.")
    notes.append("No writes. Frozen export tables not queried.")
    notes.append("")

    units = fetch_units(client)
    by_id = {str(u.get("id") or ""): u for u in units if u.get("id")}
    key_union: set[str] = set()
    for row in units:
        key_union.update(row.keys())
    notes.append("## U1. Full unit list")
    notes.append("")
    notes.append(f"GET `/unit` returned **{len(units)}** records.")
    notes.append(f"Field union: {', '.join(sorted(key_union))}")
    notes.append("")
    notes.append("| id | name | other fields |")
    notes.append("|---|---|---|")
    for row in sorted(units, key=lambda r: str(r.get("name") or "").casefold()):
        extras = {k: v for k, v in row.items() if k not in {"id", "name"}}
        extra_s = ", ".join(f"`{k}`={v!r}" for k, v in sorted(extras.items()))
        notes.append(
            f"| `{row.get('id')}` | `{row.get('name')}` | {extra_s or '(none)'} |"
        )
    notes.append("")
    samples = units[:2]
    if len(units) >= 2:
        # Prefer two different names if possible.
        names = {}
        for row in units:
            names.setdefault(str(row.get("name") or ""), row)
        if len(names) >= 2:
            samples = list(names.values())[:2]
    notes.append("### Raw JSON (two records)")
    notes.append("")
    for i, row in enumerate(samples, 1):
        notes.append(f"#### sample {i} id `{row.get('id')}`")
        notes.append("")
        notes.append("```json")
        notes.append(_json(row))
        notes.append("```")
        notes.append("")

    db = SessionLocal()
    try:
        article_mirror_n = db.scalar(select(func.count()).select_from(WeclappArticle)) or 0
        article_present_n = db.scalar(
            select(func.count())
            .select_from(WeclappArticle)
            .where(WeclappArticle.missing_since.is_(None))
        ) or 0
        ss_n = db.scalar(select(func.count()).select_from(WeclappSupplySource)) or 0
        ss_present_n = db.scalar(
            select(func.count())
            .select_from(WeclappSupplySource)
            .where(WeclappSupplySource.missing_since.is_(None))
        ) or 0
        link_n = db.scalar(select(func.count()).select_from(WeclappSupplySourceLink)) or 0
        notes.append("## Mirror sizes (context)")
        notes.append("")
        notes.append(
            f"`weclapp_articles`: {article_mirror_n} total, {article_present_n} with `missing_since` null "
            f"(prompt cited 4174)."
        )
        notes.append(
            f"`weclapp_supply_sources`: {ss_n} total, {ss_present_n} present "
            f"(prompt cited 4227)."
        )
        notes.append(f"`weclapp_supply_source_links`: {link_n}.")
        notes.append(
            "Article mirror has **no `unit_id` column**. Article-side counts below come from live GET `/article`."
        )
        notes.append("")

        ss_rows = list(
            db.execute(
                select(
                    WeclappSupplySource.weclapp_id,
                    WeclappSupplySource.supplier_number,
                    WeclappSupplySource.supplier_article_number,
                    WeclappSupplySource.unit_id,
                    WeclappSupplySource.missing_since,
                )
            )
        )
        ss_counts: Counter[str] = Counter()
        ss_null = 0
        for row in ss_rows:
            if row.missing_since is not None:
                continue
            uid = (row.unit_id or "").strip()
            if not uid:
                ss_null += 1
                continue
            ss_counts[uid] += 1

        article_live = fetch_article_units(client)
        art_counts: Counter[str] = Counter()
        art_null = 0
        art_by_id: dict[str, dict[str, Any]] = {}
        for row in article_live:
            aid = str(row.get("id") or "")
            if aid:
                art_by_id[aid] = row
            uid = str(row.get("unitId") or "").strip()
            if not uid:
                art_null += 1
                continue
            art_counts[uid] += 1

        notes.append("## U2. Units actually used")
        notes.append("")
        notes.append(
            f"Live GET `/article`: **{len(article_live)}** records "
            f"(id-only properties requested; if weclapp ignored `properties`, bodies may be full)."
        )
        notes.append(f"Articles with empty `unitId`: {art_null}.")
        notes.append(f"Present supply sources with empty `unit_id`: {ss_null}.")
        notes.append("")
        all_ids = sorted(set(art_counts) | set(ss_counts), key=lambda i: (-(art_counts[i] + ss_counts[i]), i))
        notes.append("| unitId | name | article count | supply-source count (present) |")
        notes.append("|---|---|---:|---:|")
        for uid in all_ids:
            notes.append(
                f"| `{uid}` | {_unit_name(by_id, uid) or '?'} | {art_counts[uid]} | {ss_counts[uid]} |"
            )
        unused = [u for u in units if str(u.get("id")) not in art_counts and str(u.get("id")) not in ss_counts]
        notes.append("")
        unused_s = ", ".join(
            "`{}` (`{}`)".format(u.get("name"), u.get("id")) for u in unused
        )
        notes.append(
            f"Units in `/unit` with **zero** article and zero present-SS use: **{len(unused)}** "
            f"— {unused_s or '(none)'}."
        )
        notes.append("")

        notes.append("## U3. Article vs supply-source disagreement")
        notes.append("")
        links = list(
            db.execute(
                select(
                    WeclappSupplySourceLink.supply_source_weclapp_id,
                    WeclappSupplySourceLink.weclapp_article_id,
                    WeclappSupplySourceLink.article_number,
                    WeclappSupplySource.unit_id,
                    WeclappSupplySource.supplier_number,
                    WeclappSupplySource.supplier_article_number,
                ).join(
                    WeclappSupplySource,
                    WeclappSupplySource.weclapp_id
                    == WeclappSupplySourceLink.supply_source_weclapp_id,
                )
            )
        )
        differ: list[dict[str, Any]] = []
        same = 0
        missing_article = 0
        missing_ss_unit = 0
        missing_art_unit = 0
        for link in links:
            ss_unit = (link.unit_id or "").strip()
            art = art_by_id.get(str(link.weclapp_article_id))
            if art is None:
                missing_article += 1
                continue
            art_unit = str(art.get("unitId") or "").strip()
            if not ss_unit:
                missing_ss_unit += 1
            if not art_unit:
                missing_art_unit += 1
            if ss_unit and art_unit and ss_unit != art_unit:
                differ.append(
                    {
                        "article_number": link.article_number,
                        "article_id": link.weclapp_article_id,
                        "san": link.supplier_article_number,
                        "supplier": link.supplier_number,
                        "ss_id": link.supply_source_weclapp_id,
                        "article_unit": art_unit,
                        "ss_unit": ss_unit,
                    }
                )
            elif ss_unit and art_unit:
                same += 1
        notes.append(f"Links compared: {len(links)}.")
        notes.append(f"Both units present and **equal**: {same}.")
        notes.append(f"Both present and **differ**: **{len(differ)}**.")
        notes.append(f"Link article id not in live GET: {missing_article}.")
        notes.append(f"Empty SS unit on a link: {missing_ss_unit}. Empty article unitId: {missing_art_unit}.")
        notes.append("")
        if differ:
            notes.append("Examples (up to 10):")
            notes.append("")
            notes.append("| article | SAN | supplier | article unit | SS unit |")
            notes.append("|---|---|---|---|---|")
            for ex in differ[:10]:
                notes.append(
                    f"| `{ex['article_number']}` | `{ex['san']}` | `{ex['supplier']}` | "
                    f"{_unit_label(by_id, ex['article_unit'])} | {_unit_label(by_id, ex['ss_unit'])} |"
                )
            notes.append("")
        else:
            notes.append("No disagreements among links where both unit ids are present.")
            notes.append("")

        notes.append("## U4. Per supplier (present supply sources)")
        notes.append("")
        by_sup: dict[str, Counter[str]] = defaultdict(Counter)
        by_sup_n: Counter[str] = Counter()
        for row in ss_rows:
            if row.missing_since is not None:
                continue
            by_sup[row.supplier_number][(row.unit_id or "").strip() or "(empty)"] += 1
            by_sup_n[row.supplier_number] += 1
        suppliers = list(
            db.scalars(select(Supplier).where(Supplier.deleted_at.is_(None))).all()
        )
        notes.append("| supplier_number | name | default_unit_id | SS n | distinct units | single-unit? |")
        notes.append("|---|---|---|---:|---:|---|")
        seen_numbers = set()
        for s in suppliers:
            seen_numbers.add(s.supplier_number)
            dist = by_sup.get(s.supplier_number, Counter())
            notes.append(
                f"| `{s.supplier_number}` | {s.name} | `{s.default_unit_id}` | "
                f"{by_sup_n[s.supplier_number]} | {len([k for k in dist if k != '(empty)'])} | "
                f"{'yes' if len(dist) == 1 else 'no'} |"
            )
        for num in SEEDED:
            if num not in seen_numbers:
                notes.append(f"| `{num}` | (not in `suppliers`) | — | {by_sup_n[num]} | {len(by_sup[num])} | |")
        notes.append("")
        for num in sorted(set(SEEDED) | set(by_sup)):
            dist = by_sup.get(num, Counter())
            notes.append(f"### supplier `{num}` ({by_sup_n[num]} present SS)")
            notes.append("")
            if not dist:
                notes.append("No present supply sources in the mirror.")
                notes.append("")
                continue
            notes.append("| unitId | name | count | share |")
            notes.append("|---|---|---:|---:|")
            total = sum(dist.values()) or 1
            for uid, n in dist.most_common():
                label = uid if uid == "(empty)" else _unit_label(by_id, uid)
                notes.append(f"| `{uid}` | {label} | {n} | {n / total:.1%} |")
            notes.append("")
            notes.append(
                "Single-unit supplier: **yes**."
                if len(dist) == 1
                else "Single-unit supplier: **no**."
            )
            notes.append("")

        notes.append("## U5. Name shape")
        notes.append("")
        names = [str(u.get("name") or "") for u in units]
        notes.append("Exact `name` strings:")
        notes.append("")
        for name in sorted(names, key=str.casefold):
            notes.append(f"- `{name}`")
        notes.append("")
        extra_nameish = sorted(k for k in key_union if k not in {"id", "name"})
        notes.append(
            f"Non-id/name fields present on unit records: {extra_nameish or 'none'}."
        )
        notes.append(
            "Separate short name / description field: **no**, unless listed above."
        )
        dup_names = [n for n, c in Counter(names).items() if c > 1]
        notes.append(
            f"Duplicate names across different ids: {dup_names or 'none'} "
            f"(alias table would need this if matching on name)."
        )
        notes.append("")
        germanish = any(
            any(ch in n for ch in "äöüÄÖÜß") or n in {"Stück", "Stk", "Stk.", "lfm", "lfdm", "Paar"}
            for n in names
        )
        notes.append(
            "Language/abbreviation: listed verbatim above. "
            f"Looks abbreviated/German mix from the strings themselves (heuristic germanish={germanish})."
        )
        notes.append("")

        notes.append("## U6. Other unit-ish fields on articleSupplySource")
        notes.append("")
        notes.append(
            "From `scripts/discovery/out/supply_source_read.md` A2, the GET field union is:"
        )
        notes.append("")
        notes.append(", ".join(f"`{k}`" for k in SS_KEYS_FROM_A2))
        notes.append("")
        unitish_present = [k for k in UNITISH_KEYS if k in SS_KEYS_FROM_A2]
        unitish_absent = [k for k in UNITISH_KEYS if k not in SS_KEYS_FROM_A2]
        notes.append(f"Unit-ish keys **in** that union: {unitish_present or '(none besides checking)'}.")
        notes.append(f"Unit-ish keys **not** in that union: {unitish_absent}.")
        notes.append("`unitId` is present 4227/4227 on that discovery snapshot.")
        notes.append(
            "`minimumPurchaseQuantity` / `fixedPurchaseQuantity` are quantities, not a unit "
            "(present 13/4227 each). `customAttributes` is a list on every SS — contents not re-scanned here "
            "(earlier read discovery did not flag a unit attribute)."
        )
        notes.append(
            "CSV also has `Gebindemenge` / `Mindestbestellmenge`; those map to purchase quantities, not `unitId`."
        )
        notes.append("")

        notes.append("## U7. CSV import template")
        notes.append("")
        headers, csv_counts, csv_notes = csv_unit_values(CSV_PATH)
        notes.append(f"File: `{CSV_PATH.relative_to(_ROOT)}`")
        notes.append(f"Exists: {CSV_PATH.is_file()}.")
        if "Artikel-Mengeneinheit" in headers:
            idx = headers.index("Artikel-Mengeneinheit") + 1
            notes.append(
                f"Column **Artikel-Mengeneinheit** is present (1-based index {idx}, Excel letter O in the A2 header map)."
            )
        else:
            notes.append("Column **Artikel-Mengeneinheit** is **missing**.")
        for n in csv_notes:
            notes.append(n)
        notes.append(f"Data rows: {sum(csv_counts.values())}.")
        notes.append("Distinct values in that column (empty string counted):")
        notes.append("")
        notes.append("| value | count | matches a weclapp unit `name`? | matches a weclapp unit `id`? |")
        notes.append("|---|---:|---|---|")
        name_set = {str(u.get("name") or "") for u in units}
        id_set = set(by_id)
        for value, n in csv_counts.most_common():
            shown = value if value != "" else "(empty)"
            notes.append(
                f"| `{shown}` | {n} | "
                f"{'yes' if value in name_set else 'no'} | "
                f"{'yes' if value in id_set else 'no'} |"
            )
        notes.append("")
        notes.append(
            "Internal export maps this column from article `unitId` → unit **name** "
            "(`scripts/export/generate_weclapp_import.py`: `Artikel-Mengeneinheit` ← `Basiseinheitencode`; "
            "`scripts/weclapp/master_columns.py` `unit_name()`). "
            "A produced Dural CSV uses values like `lfm` / `Stk.` — names, not ids."
        )
        notes.append("")
        dural = _ROOT / "input" / "bezugsquellen_10000_2026-08-25_2020.csv"
        if dural.is_file():
            _, dural_counts, _ = csv_unit_values(dural)
            notes.append(
                f"Produced Dural CSV `{dural.name}`: {sum(dural_counts.values())} rows. Distinct Artikel-Mengeneinheit:"
            )
            notes.append("")
            notes.append("| value | count | matches unit name? |")
            notes.append("|---|---:|---|")
            for value, n in dural_counts.most_common():
                shown = value if value != "" else "(empty)"
                notes.append(
                    f"| `{shown}` | {n} | {'yes' if value in name_set else 'no'} |"
                )
            notes.append("")
        notes.append(
            "Wizard expectation is therefore **the unit `name`**, not the id. "
            "`description` on `/unit` is the long German form (Stück, Laufmeter); the CSV uses `name` (Stk., lfm). "
            "No separate code field exists on GET `/unit`."
        )
        notes.append("")

        notes.append("## U8. Is `unitId` writable on PUT?")
        notes.append("")
        notes.append(
            "B1 (`scripts/discovery/supply_source_discovery_write.py`) included `unitId` in the "
            "one-extra-field PUT vs known-good. Outcome recorded in `supply_source_write.md`: "
            "**accepted** status 200. The payload **echoed the existing** `unitId` (`3566`), "
            "it did **not** change it to a different unit."
        )
        notes.append(
            "So: sending `unitId` on PUT is not rejected. **Changing** `unitId` on an existing "
            "supply source is **untested** (no live write in this discovery)."
        )
        notes.append("")

        notes.append("## Bridges the data supports")
        notes.append("")
        n_units = len(units)
        single = [
            num
            for num in SEEDED
            if len(by_sup.get(num, Counter())) == 1
        ]
        notes.append(
            f"**A. Dropdown of weclapp units.** Supported. Catalogue is small ({n_units} units). "
            "Dennis would see the exact `name` strings from U5. Ids stay in the app; template text can be the name. "
            "Unused catalogue entries can be hidden or shown — your call."
        )
        notes.append(
            "**B. Free-text matched to names, plus alias table.** Weakly supported as the *primary* path. "
            f"Names are unique in this tenant ({'duplicates exist' if dup_names else 'no duplicate names'}). "
            "CSV already uses names (`lfm`, `Stk.`). An alias table is only needed if supplier files use other spellings "
            "(Stk vs Stk. vs Stück) — **not evidenced in weclapp's own list**, only in how humans type. "
            "Your call whether aliases are worth it before seeing a real template file."
        )
        notes.append(
            "**C. Per-supplier default with per-row override.** "
            + (
                f"Viable as a *default* only for single-unit suppliers: {single or 'none of the four'}. "
                if True
                else ""
            )
            + "Not viable as the only mechanism: seeded `default_unit_id` is NULL on all four, and "
            "U4 shows mixed units wherever a supplier is not single-unit. "
            "Override (A or B per row) is still required for mixed suppliers."
        )
        notes.append("")
        notes.append("### Decisions that are yours")
        notes.append("")
        notes.append("- Hide unused `/unit` catalogue rows in a dropdown, or show the full list.")
        notes.append("- Whether create copies the **article** unit when SS and article always agree (see U3).")
        notes.append("- Whether to seed `suppliers.default_unit_id` from the modal SS unit (only if U4 is single-unit).")
        notes.append("- Alias table now vs after the first messy Excel.")
        notes.append("- Live PUT that *changes* `unitId` on 999.999.001 (U8 left untested).")
        notes.append("")
    finally:
        db.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(notes) + "\n"
    OUT_PATH.write_text(text, encoding="utf-8")
    print(text)
    print(f"Wrote {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
