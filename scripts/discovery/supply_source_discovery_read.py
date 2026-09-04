"""Read-only weclapp articleSupplySource discovery (Phase A).

GET only. No POST/PUT/DELETE. No database writes.

    PYTHONPATH=. python scripts/discovery/supply_source_discovery_read.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.weclapp.client import WeclappClient, WeclappError
from scripts.weclapp.config import load_config

OUT_PATH = _ROOT / "scripts" / "discovery" / "out" / "supply_source_read.md"
CSV_PATH = _ROOT / "data" / "SupplySourcesWeclapp DemoImportfile_de (28.10.2024)(1).csv"

DURAL_SUPPLIER_NUMBER = "10000"

NATIVE_PN_CANDIDATES = (
    "manufacturerPartNumber",
    "ean",
    "matchCode",
    "articleNumber",
    "internalNote",
    "shortDescription1",
    "shortDescription2",
)

ATTR_LABEL_HINTS = (
    "mpn",
    "ean",
    "gtin",
    "hersteller",
    "lieferant",
    "artikelnummer",
    "artikel-nr",
    "artikelnr",
    "part number",
    "partnumber",
    "sku",
    "herstellertyp",
    "herstellerartikel",
    "supplier",
    "manufacturer",
)


class CountingClient(WeclappClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.request_count = 0
        self.last_status: int | None = None

    @property
    def base_url(self) -> str:
        # Python 3.8 in this shell: avoid WeclappConfig.base_url (str.removesuffix).
        tenant = self.config.tenant.strip()
        suffix = ".weclapp.com"
        if tenant.endswith(suffix):
            tenant = tenant[: -len(suffix)]
        return "https://{}.weclapp.com/webapp/api/v2".format(tenant)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if method.upper() != "GET":
            raise RuntimeError(f"read probe refused non-GET: {method} {path}")
        self.request_count += 1
        return super().request(method, path, params=params, json=json)


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def describe_keys(records: list[dict[str, Any]]) -> list[str]:
    keys: dict[str, Counter[str]] = defaultdict(Counter)
    present = Counter()
    for rec in records:
        for k, v in rec.items():
            present[k] += 1
            keys[k][json_type(v)] += 1
    lines = []
    for k in sorted(keys):
        types = ", ".join(f"{t}×{c}" for t, c in sorted(keys[k].items()))
        lines.append(
            f"- `{k}`: present {present[k]}/{len(records)}; types: {types}"
        )
    return lines


def party_name(party: dict[str, Any] | None) -> str:
    if not party:
        return ""
    for key in ("company", "name", "firstName"):
        val = str(party.get(key) or "").strip()
        if val:
            return val
    return ""


def attr_value(entry: dict[str, Any]) -> str:
    for key in (
        "stringValue",
        "numberValue",
        "booleanValue",
        "dateValue",
        "selectedValueId",
        "entityId",
    ):
        if key not in entry:
            continue
        value = entry[key]
        if value is None or value == "":
            continue
        return str(value)
    refs = entry.get("entityReferences")
    if refs:
        return json.dumps(refs, ensure_ascii=False)
    return ""


def article_attr_map(
    article: dict[str, Any], id_to_label: dict[str, str]
) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in article.get("customAttributes") or []:
        if not isinstance(entry, dict):
            continue
        attr_id = str(entry.get("attributeDefinitionId") or "").strip()
        label = id_to_label.get(attr_id, attr_id)
        val = attr_value(entry).strip()
        if label:
            out[label] = val
    return out


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def collect_entity(
    client: CountingClient, entity: str
) -> tuple[list[dict[str, Any]], float, int]:
    client.request_count = 0
    t0 = time.perf_counter()
    rows = list(client.iter_pages(entity))
    elapsed = time.perf_counter() - t0
    return rows, elapsed, client.request_count


def try_filter(
    client: CountingClient, params: dict[str, Any]
) -> dict[str, Any]:
    client.request_count = 0
    t0 = time.perf_counter()
    try:
        payload = client.get("/articleSupplySource", params={**params, "pageSize": 5, "page": 1})
        elapsed = time.perf_counter() - t0
        rows = payload.get("result") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            rows = []
        return {
            "params": params,
            "ok": True,
            "status": 200,
            "elapsed_s": round(elapsed, 3),
            "result_count_this_page": len(rows),
            "sample_ids": [str(r.get("id")) for r in rows[:5] if isinstance(r, dict)],
            "error": None,
        }
    except WeclappError as exc:
        elapsed = time.perf_counter() - t0
        return {
            "params": params,
            "ok": False,
            "status": exc.status_code,
            "elapsed_s": round(elapsed, 3),
            "result_count_this_page": 0,
            "sample_ids": [],
            "error": exc.detail,
        }


def csv_columns() -> list[str]:
    header = CSV_PATH.read_text(encoding="utf-8").splitlines()[0]
    return header.split(";")


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main() -> int:
    config = load_config()
    client = CountingClient(config)
    lines: list[str] = []

    def emit(text: str = "") -> None:
        lines.append(text)
        print(text)

    emit("# articleSupplySource discovery — Phase A (read-only)")
    emit()
    emit(f"Tenant: `{config.tenant}` (token not printed).")
    emit(f"Client base URL used for GETs: tenant `{config.tenant}` via WeclappClient.")
    emit()

    emit("## Timing pulls (A8 / A10)")
    emit()

    definitions, def_s, def_n = collect_entity(client, "customAttributeDefinition")
    emit(
        f"- customAttributeDefinition: **{len(definitions)}** records, "
        f"**{def_s:.2f}s**, **{def_n}** GET requests"
    )

    sources, src_s, src_n = collect_entity(client, "articleSupplySource")
    emit(
        f"- articleSupplySource (full unfiltered paged pull): **{len(sources)}** records, "
        f"**{src_s:.2f}s** wall-clock, **{src_n}** GET requests"
    )

    articles, art_s, art_n = collect_entity(client, "article")
    emit(
        f"- article: **{len(articles)}** records, "
        f"**{art_s:.2f}s**, **{art_n}** GET requests"
    )
    emit()

    supplier_ids = sorted(
        {str(s.get("supplierId") or "").strip() for s in sources if s.get("supplierId")}
    )
    party_t0 = time.perf_counter()
    client.request_count = 0
    parties: dict[str, dict[str, Any]] = {}
    party_errors: list[str] = []
    for sid in supplier_ids:
        try:
            parties[sid] = client.get(f"/party/id/{sid}")
        except WeclappError as exc:
            party_errors.append(f"{sid}: {exc.status_code} {exc.detail}")
    party_s = time.perf_counter() - party_t0
    emit(
        f"- party GET by id for {len(supplier_ids)} distinct supplierIds: "
        f"**{party_s:.2f}s**, **{client.request_count}** GET requests"
    )
    if party_errors:
        emit("- party fetch errors:")
        for err in party_errors:
            emit(f"  - {err}")
    emit()

    articles_by_id = {str(a.get("id")): a for a in articles}
    sources_by_id = {str(s.get("id")): s for s in sources}
    id_to_label = {}
    for d in definitions:
        attr_id = str(d.get("id") or "").strip()
        label = str(d.get("label") or d.get("attributeKey") or attr_id).strip()
        if attr_id:
            id_to_label[attr_id] = label

    currencies, cur_s, cur_n = collect_entity(client, "currency")
    emit(
        f"- currency: **{len(currencies)}** records, **{cur_s:.2f}s**, **{cur_n}** GET"
    )
    currency_by_id = {str(c.get("id")): c for c in currencies}
    emit()

    article_key_union = sorted({k for a in articles for k in a.keys()})
    emit("### Article native keys (union) — needed because SS has no articleId")
    emit()
    emit(", ".join(f"`{k}`" for k in article_key_union))
    emit()
    n_primary = sum(1 for a in articles if nonempty(a.get("primarySupplySourceId")))
    n_ss_list = sum(1 for a in articles if a.get("supplySources"))
    emit(f"- articles with primarySupplySourceId: **{n_primary}/{len(articles)}**")
    emit(f"- articles with non-empty supplySources list: **{n_ss_list}/{len(articles)}**")
    sample_rel = next((a for a in articles if a.get("supplySources")), None)
    if sample_rel:
        emit("Sample `supplySources` + `primarySupplySourceId` from one article:")
        emit()
        emit("```json")
        emit(
            json.dumps(
                {
                    "articleNumber": sample_rel.get("articleNumber"),
                    "id": sample_rel.get("id"),
                    "primarySupplySourceId": sample_rel.get("primarySupplySourceId"),
                    "supplySources": sample_rel.get("supplySources"),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        emit("```")
        emit()

    def article_ss_ids(article: dict[str, Any]) -> set[str]:
        ids: set[str] = set()
        primary = str(article.get("primarySupplySourceId") or "").strip()
        if primary:
            ids.add(primary)
        for ref in article.get("supplySources") or []:
            if not isinstance(ref, dict):
                continue
            sid = str(
                ref.get("articleSupplySourceId") or ref.get("id") or ""
            ).strip()
            if sid:
                ids.add(sid)
        return ids

    ss_to_article_ids: dict[str, list[str]] = defaultdict(list)
    article_to_ss: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in articles:
        aid = str(a.get("id"))
        for ssid in article_ss_ids(a):
            ss_to_article_ids[ssid].append(aid)
            rec = sources_by_id.get(ssid)
            if rec:
                article_to_ss[aid].append(rec)

    orphan_ss = [s for s in sources if str(s.get("id")) not in ss_to_article_ids]
    emit(
        f"Join: **{len(ss_to_article_ids)}** supply sources referenced from ≥1 article; "
        f"**{len(orphan_ss)}** supply sources not referenced by any article "
        f"(via primarySupplySourceId / supplySources)."
    )
    emit()
    if orphan_ss[:5]:
        emit("First 5 unreferenced SS ids / articleNumber / supplierId:")
        for s in orphan_ss[:5]:
            emit(
                f"- `{s.get('id')}` articleNumber `{s.get('articleNumber')}` "
                f"supplierId `{s.get('supplierId')}`"
            )
        emit()

    # ------------------------------------------------------------------ A1
    emit("## A1. Supplier inventory")
    emit()
    emit(
        "**Observed:** `articleSupplySource` has **no** `articleId` and **no** "
        "`supplierArticleNumber`. The supplier part number lives in SS.`articleNumber`. "
        "Article linkage is on the **article** entity (`primarySupplySourceId`, "
        "`supplySources[]`). Distinct-article counts below use that join."
    )
    emit()
    by_supplier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sources:
        sid = str(s.get("supplierId") or "").strip() or "(missing supplierId)"
        by_supplier[sid].append(s)

    rows_a1: list[tuple[int, str, str, str, int, int]] = []
    for sid, recs in by_supplier.items():
        party = parties.get(sid)
        supplier_number = ""
        name = ""
        if party:
            supplier_number = str(
                party.get("supplierNumber") or party.get("customerNumber") or ""
            ).strip()
            name = party_name(party)
        else:
            sample = recs[0]
            supplier_number = str(sample.get("supplierNumber") or "").strip()
            name = str(sample.get("supplierName") or "").strip()
        linked_articles: set[str] = set()
        for rec in recs:
            linked_articles.update(ss_to_article_ids.get(str(rec.get("id")), []))
        rows_a1.append(
            (len(recs), supplier_number, sid, name, len(recs), len(linked_articles))
        )
    rows_a1.sort(key=lambda r: (-r[0], r[1], r[2]))

    emit(
        "| supplierNumber | party id | party name | supply sources | distinct articles |"
    )
    emit("|---|---|---|---:|---:|")
    for _, sn, sid, name, n_ss, n_art in rows_a1:
        emit(
            f"| {md_escape(sn) or '—'} | `{sid}` | {md_escape(name) or '—'} "
            f"| {n_ss} | {n_art} |"
        )
    emit()
    emit(f"Distinct suppliers (by supplierId): **{len(by_supplier)}**")
    emit()

    # ------------------------------------------------------------------ A2
    emit("## A2. Supply-source field shape")
    emit()

    def pick_samples(supplier_number: str, n: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for sid, recs in by_supplier.items():
            party = parties.get(sid)
            sn = ""
            if party:
                sn = str(party.get("supplierNumber") or "").strip()
            if not sn:
                sn = str(recs[0].get("supplierNumber") or "").strip()
            if sn == supplier_number:
                out.extend(recs[:n])
                break
        return out[:n]

    samples_10000 = pick_samples(DURAL_SUPPLIER_NUMBER, 3)
    other_sn = next(
        (sn for _, sn, *_ in rows_a1 if sn and sn != DURAL_SUPPLIER_NUMBER),
        "",
    )
    samples_other = pick_samples(other_sn, 3) if other_sn else []

    all_keys_union = sorted({k for rec in sources for k in rec.keys()})
    emit("### Union of keys across all supply sources")
    emit()
    emit(", ".join(f"`{k}`" for k in all_keys_union))
    emit()
    emit("### Key presence / types across all records")
    emit()
    for line in describe_keys(sources):
        emit(line)
    emit()

    emit(f"### Raw JSON — supplier {DURAL_SUPPLIER_NUMBER} (n={len(samples_10000)})")
    emit()
    if not samples_10000:
        emit("**No supply sources found for supplier 10000.**")
        emit()
    else:
        emit("Key/type/null for these 3:")
        emit()
        for line in describe_keys(samples_10000):
            emit(line)
        emit()
        for i, rec in enumerate(samples_10000, 1):
            emit(f"#### sample {i} (id `{rec.get('id')}`)")
            emit()
            emit("```json")
            emit(json.dumps(rec, ensure_ascii=False, indent=2, default=str))
            emit("```")
            emit()

    emit(
        f"### Raw JSON — other supplier `{other_sn or 'none'}` "
        f"(n={len(samples_other)})"
    )
    emit()
    if not samples_other:
        emit("**No other supplier with supply sources.**")
        emit()
    else:
        emit("Key/type/null for these 3:")
        emit()
        for line in describe_keys(samples_other):
            emit(line)
        emit()
        for i, rec in enumerate(samples_other, 1):
            emit(f"#### sample {i} (id `{rec.get('id')}`)")
            emit()
            emit("```json")
            emit(json.dumps(rec, ensure_ascii=False, indent=2, default=str))
            emit()

    # ------------------------------------------------------------------ A3
    emit("## A3. Version field")
    emit()
    versions = [s.get("version") if "version" in s else "<MISSING KEY>" for s in sources]
    with_key = sum(1 for s in sources if "version" in s)
    non_null = sum(1 for s in sources if s.get("version") is not None)
    type_counts = Counter(json_type(s.get("version") if "version" in s else None) for s in sources)
    if "version" in sources[0] if sources else {}:
        sample_vals = [s.get("version") for s in sources[:10]]
    else:
        sample_vals = []
    emit(f"- key `version` present on **{with_key}/{len(sources)}** records")
    emit(f"- non-null on **{non_null}/{len(sources)}**")
    emit(f"- types: {dict(type_counts)}")
    emit(f"- first 10 values: `{sample_vals}`")
    emit("- PUT enforcement: **not tested** (Phase B).")
    emit()

    # ------------------------------------------------------------------ A4
    emit("## A4. Currency and price-entry")
    emit()
    emit(
        "No top-level currency field on articleSupplySource. Currency lives on "
        "nested `articlePrices[].currencyId` (observed)."
    )
    emit()
    emit("Currency id catalog from GET /currency:")
    emit()
    for c in currencies:
        emit(
            f"- id `{c.get('id')}` name `{c.get('name')}` iso `{c.get('isoCode') or c.get('currencyCode')}` keys={sorted(c.keys())}"
        )
    emit()

    price_cur = Counter()
    price_start = Counter()
    n_prices = 0
    n_ss_with_prices = 0
    distinct_price_keys: set[str] = set()
    for s in sources:
        prices = s.get("articlePrices") or []
        if prices:
            n_ss_with_prices += 1
        for p in prices:
            if not isinstance(p, dict):
                continue
            n_prices += 1
            distinct_price_keys.update(p.keys())
            cid = str(p.get("currencyId") or "")
            iso = ""
            cur = currency_by_id.get(cid) or {}
            iso = str(cur.get("isoCode") or cur.get("currencyCode") or cur.get("name") or "")
            price_cur[f"currencyId={cid} iso/name={iso!r}"] += 1
            if "startDate" in p:
                price_start["has startDate"] += 1
            else:
                price_start["missing startDate key"] += 1
    emit(f"Supply sources with articlePrices: **{n_ss_with_prices}/{len(sources)}**")
    emit(f"Total nested price rows: **{n_prices}**")
    emit(f"Union of articlePrices keys: {sorted(distinct_price_keys)}")
    emit()
    emit("Distinct currencyId on nested prices (count = price rows, not SS):")
    emit()
    for val, n in price_cur.most_common():
        emit(f"- `{val}` → {n}")
    emit()
    emit(f"startDate presence on price rows: {dict(price_start)}")
    emit()

    # current price = no endDate
    current_cur_by_ss = Counter()
    for s in sources:
        currents = []
        for p in s.get("articlePrices") or []:
            if isinstance(p, dict) and p.get("endDate") is None:
                currents.append(p)
        cids = tuple(sorted({str(p.get("currencyId")) for p in currents}))
        current_cur_by_ss[str(cids)] += 1
    emit("currencyId on prices with endDate=null/absent, per supply source:")
    emit()
    for val, n in current_cur_by_ss.most_common():
        emit(f"- `{val}` → {n} supply sources")
    emit()


    party_currencies: Counter[str] = Counter()
    for sid, recs in by_supplier.items():
        party = parties.get(sid)
        if not party:
            party_currencies["(party missing)"] += len(recs)
            continue
        blob = []
        for k, v in party.items():
            if "currenc" in k.lower():
                blob.append(f"{k}={v!r}")
        party_currencies["; ".join(blob) or "(no currency keys on party)"] += 1
    emit("Party currency keys (one count per distinct supplier, not per SS):")
    emit()
    for val, n in party_currencies.most_common():
        emit(f"- `{val}` → {n} suppliers")
    emit()

    cols = csv_columns()
    emit("CSV template columns (1-based / Excel letter):")
    emit()
    letters = []
    for i, name in enumerate(cols, 1):
        # Excel letters
        n = i
        letter = ""
        while n:
            n, rem = divmod(n - 1, 26)
            letter = chr(65 + rem) + letter
        letters.append((letter, name))
        if letter in {"R", "V", "W"} or name in {
            "Preis-Eintritt",
            "Zugehörigen Verkaufsartikel erstellen oder aktualisieren",
            "Verkaufsartikel-Nummer",
        }:
            emit(f"- **{letter}** = `{name}`")
    emit()
    emit("Full header for reference:")
    emit()
    emit(";".join(f"{let}:{name}" for let, name in letters))
    emit()

    # Heuristic mapping from live field names
    date_like = [
        k
        for k in all_keys_union
        if any(
            tok in k.lower()
            for tok in ("valid", "from", "start", "date", "entry", "eintritt")
        )
    ]
    emit(f"Supply-source keys that look date-ish: {date_like}")
    emit()
    article_link_keys = [
        k
        for k in all_keys_union
        if any(
            tok in k.lower()
            for tok in ("article", "sales", "create", "relation")
        )
    ]
    emit(f"Supply-source keys that look article-link-ish: {article_link_keys}")
    emit()

    emit("### Column mapping (evidence labeled)")
    emit()
    emit(
        "- **R / Preis-Eintritt** → nested `articlePrices[].startDate` (epoch ms). "
        "**Evidence: field-name** (startDate = price valid-from). "
        "`createdDate`/`lastModifiedDate` on the SS itself are audit timestamps, not price entry. "
        "Value-match vs a known CSV row: **not done** in this probe (no CSV row joined)."
    )
    emit(
        "- **V / Zugehörigen Verkaufsartikel erstellen oder aktualisieren**: "
        "no ja/nein field on GET articleSupplySource. **Guess:** CSV-wizard-only, not persisted."
    )
    emit(
        "- **W / Verkaufsartikel-Nummer**: SS.`articleNumber` is **not** the PROSEMA number "
        "(samples are supplier-style like `09018030`). The sales-article link is the reverse "
        "join (article.supplySources → SS id). **Inference:** W is the article.articleNumber "
        "of the linked sales article, not a field stored on the SS GET body. "
        "Direct field-name match on SS: **none**."
    )
    emit(
        "- **D / Lieferantenartikelnummer** → SS.`articleNumber`. **Evidence: value shape** "
        "(not PROSEMA MMM.SSS.NNNN) plus missing `supplierArticleNumber` key."
    )
    emit()

    emit("Sample current-price startDate values (prices with no endDate):")
    shown = 0
    for rec in sources:
        for p in rec.get("articlePrices") or []:
            if not isinstance(p, dict) or p.get("endDate") is not None:
                continue
            sd = p.get("startDate")
            human = ""
            if isinstance(sd, int):
                human = datetime.fromtimestamp(sd / 1000.0, tz=timezone.utc).isoformat()
            emit(
                f"- SS `{rec.get('id')}` SS.articleNumber `{rec.get('articleNumber')}` "
                f"startDate `{sd!r}` utc `{human}` price `{p.get('price')}` currencyId `{p.get('currencyId')}`"
            )
            shown += 1
            break
        if shown >= 8:
            break
    emit()

    # ------------------------------------------------------------------ A5
    emit("## A5. Supplier article number on the article itself")
    emit()

    emit(
        "SAN on the supply source is `articleNumber` (there is no "
        "`supplierArticleNumber` key). Comparisons below use that field via the "
        "article→SS join."
    )
    emit()
    n_san_eq_prosema = 0
    for a in articles:
        pro = str(a.get("articleNumber") or "").strip()
        for rec in article_to_ss.get(str(a.get("id")), []):
            if str(rec.get("articleNumber") or "").strip() == pro:
                n_san_eq_prosema += 1
                break
    emit(
        f"Articles whose own articleNumber equals a linked SS.articleNumber: "
        f"**{n_san_eq_prosema}/{len(articles)}**"
    )
    emit()
    labels_all = sorted({d and id_to_label.get(str(d.get("id")), "") for d in definitions})
    _ = labels_all
    emit("### customAttributeDefinition inventory")
    emit()
    emit("| id | label | attributeKey | entity | type |")
    emit("|---|---|---|---|---|")
    for d in sorted(definitions, key=lambda x: str(x.get("label") or "")):
        emit(
            f"| `{d.get('id')}` | {md_escape(str(d.get('label') or ''))} | "
            f"`{d.get('attributeKey')}` | `{d.get('entityName') or d.get('entityType') or ''}` | "
            f"`{d.get('attributeType') or d.get('type') or ''}` |"
        )
    emit()

    candidate_labels = []
    for d in definitions:
        label = str(d.get("label") or d.get("attributeKey") or "").strip()
        blob = label.lower()
        if any(h in blob for h in ATTR_LABEL_HINTS):
            candidate_labels.append(label)
    candidate_labels = sorted(set(candidate_labels))
    emit(f"Custom-attribute labels treated as PN candidates (name heuristic): {candidate_labels}")
    emit()
    emit(
        "Also reporting every custom attribute that is non-empty on ≥1 article, "
        "so a poorly named field is not missed."
    )
    emit()

    def ss_numbers(article_id: str) -> list[str]:
        out = []
        for rec in article_to_ss.get(article_id, []):
            sn = str(rec.get("articleNumber") or "").strip()
            sid = str(rec.get("supplierId") or "")
            party = parties.get(sid)
            sup_no = (
                str(party.get("supplierNumber") or "").strip()
                if party
                else ""
            )
            if sn:
                out.append(f"{sup_no}:{sn}")
        return out

    def equal_any(val: str, article_id: str) -> tuple[bool, str]:
        targets = []
        for rec in article_to_ss.get(article_id, []):
            san = str(rec.get("articleNumber") or "").strip()
            if san:
                targets.append(san)
        if val and val in targets:
            return True, "equals linked SS.articleNumber"
        if val and any(val == t.replace(" ", "") for t in targets):
            return True, "equals after stripping spaces"
        return False, "does not equal any linked SS.articleNumber"

    emit("### Native article fields")
    emit()
    extra_native = [k for k in article_key_union if any(
        h in k.lower() for h in ("manufacturer", "ean", "part", "sku", "gtin", "mpn")
    )]
    emit(f"Extra native keys matching manufacturer/ean/part/sku/gtin/mpn: {extra_native}")
    emit()
    for field in list(NATIVE_PN_CANDIDATES) + [k for k in extra_native if k not in NATIVE_PN_CANDIDATES]:
        nonempty_arts = [a for a in articles if nonempty(a.get(field))]
        emit(f"#### `{field}` — non-empty on **{len(nonempty_arts)}/{len(articles)}** articles")
        emit()
        shown = 0
        eq_n = 0
        checked = 0
        for a in nonempty_arts:
            val = a.get(field)
            sval = str(val).strip() if val is not None else ""
            aid = str(a.get("id"))
            eq, why = equal_any(sval, aid)
            checked += 1
            if eq:
                eq_n += 1
            if shown < 5:
                emit(
                    f"- articleNumber `{a.get('articleNumber')}` {field} `{sval}` | "
                    f"SS.articleNumber: {ss_numbers(aid) or '—'} | match: {why}"
                )
                shown += 1
        if checked:
            emit(
                f"- equality vs linked SS.articleNumber: **{eq_n}/{checked}**"
            )
        emit()

    emit("### Custom attributes (all labels with any non-empty value)")
    emit()
    label_hits: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
    for a in articles:
        amap = article_attr_map(a, id_to_label)
        for label, val in amap.items():
            if val:
                label_hits[label].append((a, val))

    for label in sorted(label_hits, key=lambda x: (-len(label_hits[x]), x)):
        hits = label_hits[label]
        emit(f"#### attr `{label}` — non-empty on **{len(hits)}/{len(articles)}** articles")
        emit()
        eq_n = 0
        for a, val in hits:
            eq, _ = equal_any(val, str(a.get("id")))
            if eq:
                eq_n += 1
        emit(f"- equality vs linked SS.articleNumber: **{eq_n}/{len(hits)}**")
        for a, val in hits[:5]:
            aid = str(a.get("id"))
            _, why = equal_any(val, aid)
            emit(
                f"- articleNumber `{a.get('articleNumber')}` value `{val}` | "
                f"SANs: {ss_numbers(aid) or '—'} | match: {why}"
            )
        emit()

    # ------------------------------------------------------------------ A6
    emit("## A6. Rabattcode population")
    emit()
    rabatt_hits: list[tuple[dict[str, Any], str]] = []
    for a in articles:
        amap = article_attr_map(a, id_to_label)
        val = (amap.get("Rabattcode") or "").strip()
        if val:
            rabatt_hits.append((a, val))
    emit(f"Articles with non-empty Rabattcode: **{len(rabatt_hits)}/{len(articles)}**")
    emit()
    val_counts = Counter(v for _, v in rabatt_hits)
    emit("Distinct Rabattcode values:")
    emit()
    for val, n in val_counts.most_common():
        emit(f"- `{val}` → {n}")
    emit()

    emit("Cross-tab: Rabattcode × suppliers on that article's supply sources")
    emit()
    emit("| Rabattcode | supplierNumber(s) | article count |")
    emit("|---|---|---:|")
    xtab: Counter[tuple[str, str]] = Counter()
    for a, rval in rabatt_hits:
        aid = str(a.get("id"))
        sups = set()
        for rec in article_to_ss.get(aid, []):
            sid = str(rec.get("supplierId") or "")
            party = parties.get(sid)
            sn = (
                str(party.get("supplierNumber") or "").strip()
                if party
                else ""
            )
            name = party_name(party) if party else ""
            sups.add(f"{sn} {name}".strip() or sid or "(none)")
        key = ", ".join(sorted(sups)) if sups else "(no supply sources)"
        xtab[(rval, key)] += 1
    for (rval, sups), n in sorted(xtab.items(), key=lambda x: (-x[1], x[0][0], x[0][1])):
        emit(f"| `{md_escape(rval)}` | {md_escape(sups)} | {n} |")
    emit()

    # ------------------------------------------------------------------ A7
    emit("## A7. Duplicate supply sources")
    emit()
    pair_ss: dict[tuple[str, str], list[str]] = defaultdict(list)
    for a in articles:
        aid = str(a.get("id"))
        for rec in article_to_ss.get(aid, []):
            sid = str(rec.get("supplierId") or "")
            pair_ss[(aid, sid)].append(str(rec.get("id")))
    multi_ss = {k: v for k, v in pair_ss.items() if len(set(v)) > 1}
    emit(
        f"Articles with more than one supply source for the same supplier: "
        f"**{len(multi_ss)}** (article,supplier) pairs"
    )
    emit()
    for i, ((aid, sid), ids) in enumerate(sorted(multi_ss.items(), key=lambda x: -len(set(x[1])))[:10], 1):
        art = articles_by_id.get(aid, {})
        party = parties.get(sid)
        emit(
            f"{i}. articleNumber `{art.get('articleNumber')}` articleId `{aid}` "
            f"supplier `{party.get('supplierNumber') if party else ''} {party_name(party)}` "
            f"party `{sid}` — {len(set(ids))} SS ids: {sorted(set(ids))}"
        )
    if not multi_ss:
        emit("(none)")
    emit()

    san_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rec in sources:
        san = str(rec.get("articleNumber") or "").strip()
        sid = str(rec.get("supplierId") or "")
        if not san:
            continue
        for art_id in ss_to_article_ids.get(str(rec.get("id")), []):
            san_pair[(san, sid)].append(art_id)
        if not ss_to_article_ids.get(str(rec.get("id"))):
            san_pair[(san, sid)].append(f"UNLINKED_SS:{rec.get('id')}")
    multi_san = {k: v for k, v in san_pair.items() if len(set(v)) > 1}
    emit(
        f"(SS.articleNumber, supplier) pairs on more than one article "
        f"(or unlinked SS + article): **{len(multi_san)}**"
    )
    emit()
    for i, ((san, sid), art_ids) in enumerate(
        sorted(multi_san.items(), key=lambda x: -len(set(x[1])))[:10], 1
    ):
        party = parties.get(sid)
        nums = []
        for a in sorted(set(art_ids)):
            if a.startswith("UNLINKED_SS:"):
                nums.append(a)
            else:
                nums.append(str(articles_by_id.get(a, {}).get("articleNumber") or a))
        emit(
            f"{i}. SAN `{san}` supplier `{party.get('supplierNumber') if party else ''} "
            f"{party_name(party)}` → {nums}"
        )
    if not multi_san:
        emit("(none)")
    emit()
    empty_san = sum(1 for rec in sources if not str(rec.get("articleNumber") or "").strip())
    emit(f"Supply sources with empty articleNumber: **{empty_san}**")
    emit()

    # leftover placeholder to keep following A8 intact
    emit()
    emit("## A7b (join sanity)")
    emit()
    n_multi_link = sum(1 for ids in ss_to_article_ids.values() if len(set(ids)) > 1)
    emit(
        f"Supply sources linked from more than one article: **{n_multi_link}** "
        f"(incident-style shared SS)."
    )
    emit()
    for i, (ssid, aids) in enumerate(
        sorted(
            ((k, v) for k, v in ss_to_article_ids.items() if len(set(v)) > 1),
            key=lambda x: -len(set(x[1])),
        )[:10],
        1,
    ):
        rec = sources_by_id.get(ssid, {})
        nums = [str(articles_by_id.get(a, {}).get("articleNumber") or a) for a in sorted(set(aids))]
        emit(
            f"{i}. SS `{ssid}` SAN `{rec.get('articleNumber')}` articles {nums}"
        )
    emit()

    # ------------------------------------------------------------------ A8 PLACEHOLDER
    _a8_keep = True
    if _a8_keep:
        pass

    # ------------------------------------------------------------------ A8
    emit("## A8. Server-side filtering")
    emit()
    sample_sid = ""
    sample_sn = DURAL_SUPPLIER_NUMBER
    for _, sn, sid, *_ in rows_a1:
        if sn == DURAL_SUPPLIER_NUMBER:
            sample_sid = sid
            break
    if not sample_sid and rows_a1:
        sample_sid = rows_a1[0][2]
        sample_sn = rows_a1[0][1]
    sample_san = str(sources[0].get("articleNumber") or "") if sources else ""
    sample_article_id = str(articles[0].get("id") or "") if articles else ""

    filter_attempts = [
        {"supplierId-eq": sample_sid},
        {"supplierNumber-eq": sample_sn},
        {"partyId-eq": sample_sid},
        {"supplier-eq": sample_sid},
        {"articleId-eq": sample_article_id},
        {"articleNumber-eq": sample_san},
    ]
    emit(f"Filter target supplierId=`{sample_sid}` supplierNumber=`{sample_sn}`")
    emit(f"Also trying articleNumber-eq=`{sample_san}` articleId-eq=`{sample_article_id}`")
    emit()
    for params in filter_attempts:
        clean = {k: str(v) for k, v in params.items() if v not in ("", None)}
        if not clean:
            continue
        result = try_filter(client, clean)
        emit(f"### `{clean}`")
        emit()
        emit("```json")
        emit(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        emit("```")
        emit()
        if result["ok"] and result["result_count_this_page"] > 0:
            check = list(client.iter_pages("articleSupplySource", params=clean))
            sid_set = {str(r.get("supplierId")) for r in check}
            san_set = {str(r.get("articleNumber")) for r in check}
            emit(
                f"Full paged pull with this filter: **{len(check)}** records; "
                f"distinct supplierId: `{sorted(sid_set)[:8]}`; "
                f"distinct SS.articleNumber count: {len(san_set)}"
            )
            emit()

    emit(
        f"Full unfiltered pull (from A10): **{len(sources)}** records, "
        f"**{src_s:.2f}s**, **{src_n}** requests."
    )
    emit()

    # ------------------------------------------------------------------ A9
    emit("## A9. Articles without a supply source for a given supplier")
    emit()
    dural_sid = ""
    for _, sn, sid, name, *_ in rows_a1:
        if sn == DURAL_SUPPLIER_NUMBER or "dural" in name.lower():
            dural_sid = sid
            break
    non_dural = [
        r for r in rows_a1 if r[2] != dural_sid and r[1] != DURAL_SUPPLIER_NUMBER
    ]
    if not non_dural:
        emit("**No non-Dural supplier with supply sources.**")
    else:
        largest = non_dural[0]
        _, sn, sid, name, n_ss, n_art = largest
        with_ss = set()
        for rec in by_supplier.get(sid, []):
            with_ss.update(ss_to_article_ids.get(str(rec.get("id")), []))
        without = [a for a in articles if str(a.get("id")) not in with_ss]
        emit(
            f"Largest non-Dural supplier: number `{sn}` party `{sid}` name `{name}` "
            f"({n_ss} supply sources, {n_art} distinct linked articles)."
        )
        emit(f"Total articles in tenant: **{len(articles)}**")
        emit(f"Articles with ≥1 SS for this supplier: **{len(with_ss)}**")
        emit(
            f"Articles with **no** SS for this supplier (create-path population): "
            f"**{len(without)}**"
        )
        emit("Meaningful data? " + ("yes, some linked articles" if n_art else "SS exist but join found 0 articles — check orphans"))
    emit()

    # ------------------------------------------------------------------ design flags
    emit("## Design-assumption flags (from Phase A only)")
    emit()
    emit("- Phase B was **not** run.")
    emit("- See A5 for whether a supplier PN lives on the article (tier-3 matching).")
    emit("- See A7 for uniqueness of (D, F) analogue (SS.articleNumber + supplier).")
    emit("- See A8 for whether full-tenant paging can be avoided.")
    emit()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
