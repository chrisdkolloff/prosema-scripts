"""Throwaway: measure JSONB field shapes on the current article snapshot."""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

from sqlalchemy import select, text

from app.config import settings
from app.db import SessionLocal
from app.models import ArticleSnapshot, ArticleSnapshotRow, Hauptgruppe
from core.article_fields import BY_LABEL, IMPORT_COLUMNS, FIELDS

IMPORT_SET = frozenset(IMPORT_COLUMNS)
NUMBER_TYPES = {f.label for f in FIELDS if f.field_type == "number"}
QUANTITY_NEEDLES = (
    "preis",
    "gewicht",
    "breite",
    "höhe",
    "hohe",
    "länge",
    "lange",
    "menge",
    "mm",
    "kg",
    "eur",
    "chf",
    "rabatt",
    "prozent",
)

CODE_RE = re.compile(r"^[0-9]{3}$")

# Exclusive buckets, most specific first.
RE_UNIT = re.compile(
    r"""(?x)
    ^
    [+-]?
    [\d\s.'’,]+
    \s*
    (
        %
        | €
        | kg | g | mm | cm | m | t
        | eur | chf | usd | gbp
        | stk\.? | stück
        | prozent
    )
    \s*$
    """,
    re.IGNORECASE,
)
RE_APOSTROPHE = re.compile(r"^[+-]?\d{1,3}(?:'\d{3})+(?:[.,]\d+)?$")
RE_DOT_THOUSANDS = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?$")
RE_COMMA_DECIMAL = re.compile(r"^[+-]?\d+,\d+$")
RE_DOT_DECIMAL = re.compile(r"^[+-]?\d+\.\d+$")
RE_INTEGER = re.compile(r"^[+-]?\d+$")

BUCKETS = (
    "plain integer",
    "dot decimal",
    "comma decimal",
    "apostrophe thousands",
    "dot thousands",
    "with unit or currency",
    "anything else",
)


def is_quantity_key(key: str) -> bool:
    if key in NUMBER_TYPES:
        return True
    folded = key.casefold()
    return any(needle in folded for needle in QUANTITY_NEEDLES)


def classify(value: str) -> str:
    raw = value.strip()
    if RE_UNIT.match(raw):
        return "with unit or currency"
    if RE_APOSTROPHE.match(raw):
        return "apostrophe thousands"
    if RE_DOT_THOUSANDS.match(raw):
        return "dot thousands"
    if RE_COMMA_DECIMAL.match(raw):
        return "comma decimal"
    if RE_DOT_DECIMAL.match(raw):
        return "dot decimal"
    if RE_INTEGER.match(raw):
        return "plain integer"
    return "anything else"


def md_escape(value: object) -> str:
    text_value = str(value).replace("|", "\\|").replace("\n", "\\n")
    if text_value == "":
        return "`(empty)`"
    return text_value


def main() -> None:
    tenant = settings.weclapp_tenant.strip()
    db = SessionLocal()
    try:
        snapshot = db.scalars(
            select(ArticleSnapshot)
            .where(
                ArticleSnapshot.status == "complete",
                ArticleSnapshot.weclapp_tenant == tenant,
            )
            .order_by(ArticleSnapshot.created_at.desc())
            .limit(1)
        ).first()
        if snapshot is None:
            print("No complete snapshot for tenant", tenant)
            return

        print("# Snapshot field-format report")
        print()
        print(f"- **id:** `{snapshot.id}`")
        print(f"- **created_at:** `{snapshot.created_at.isoformat()}`")
        print(f"- **row_count:** {snapshot.row_count}")
        print(f"- **non_conforming_number_count:** {snapshot.non_conforming_number_count}")
        print(f"- **weclapp_tenant:** `{snapshot.weclapp_tenant}`")
        print()

        rows = list(
            db.scalars(
                select(ArticleSnapshotRow).where(
                    ArticleSnapshotRow.snapshot_id == snapshot.id
                )
            )
        )
        n_rows = len(rows)

        present: Counter[str] = Counter()
        nonempty: Counter[str] = Counter()
        empty_string: Counter[str] = Counter()
        values_by_key: dict[str, list[str]] = defaultdict(list)
        all_keys: set[str] = set()

        for row in rows:
            data = row.data if isinstance(row.data, dict) else {}
            for key, raw in data.items():
                all_keys.add(key)
                present[key] += 1
                text_value = "" if raw is None else str(raw)
                if text_value == "":
                    empty_string[key] += 1
                else:
                    nonempty[key] += 1
                    values_by_key[key].append(text_value)

        print("## A. Key inventory")
        print()
        print(
            "| key | in IMPORT_COLUMNS | source | rows with key | non-empty | empty string |"
        )
        print("|---|---|---|---:|---:|---:|")
        for key in sorted(all_keys, key=lambda k: (-nonempty[k], k)):
            in_import = key in IMPORT_SET
            source = "import" if in_import else "master-export extra"
            print(
                f"| {md_escape(key)} | {str(in_import).lower()} | {source} | "
                f"{present[key]} | {nonempty[key]} | {empty_string[key]} |"
            )
        print()
        print(f"Union key count: **{len(all_keys)}**. Snapshot rows loaded: **{n_rows}**.")
        print()

        print("## B. Numeric parse rates")
        print()
        candidate_keys = sorted(k for k in all_keys if is_quantity_key(k))
        print(
            "| key | catalogue type | non-empty | integer | dot decimal | comma decimal | "
            "apostrophe thousands | dot thousands | unit/currency | anything else |"
        )
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        else_examples: dict[str, list[str]] = {}
        for key in candidate_keys:
            counts = Counter()
            others: list[str] = []
            for value in values_by_key[key]:
                bucket = classify(value)
                counts[bucket] += 1
                if bucket == "anything else" and len(others) < 10 and value not in others:
                    others.append(value)
            field = BY_LABEL.get(key)
            cat_type = field.field_type if field is not None else "(not in catalogue)"
            print(
                f"| {md_escape(key)} | {cat_type} | {nonempty[key]} | "
                f"{counts['plain integer']} | {counts['dot decimal']} | "
                f"{counts['comma decimal']} | {counts['apostrophe thousands']} | "
                f"{counts['dot thousands']} | {counts['with unit or currency']} | "
                f"{counts['anything else']} |"
            )
            if others:
                else_examples[key] = others
        print()
        if else_examples:
            print("### B. Anything-else examples")
            print()
            for key, examples in else_examples.items():
                print(f"**{key}**")
                print()
                print("| # | verbatim |")
                print("|---:|---|")
                for i, example in enumerate(examples, start=1):
                    print(f"| {i} | `{example}` |")
                print()
        else:
            print("No values fell into the anything-else bucket.")
            print()

        print("## C. Low-cardinality candidates")
        print()
        print("| key | distinct non-empty | top values (value × count) |")
        print("|---|---:|---|")
        low = 0
        for key in sorted(all_keys):
            freq = Counter(values_by_key[key])
            distinct = len(freq)
            if distinct == 0 or distinct > 50:
                continue
            low += 1
            top = freq.most_common(20)
            rendered = ", ".join(f"`{md_escape(v)}` × {c}" for v, c in top)
            print(f"| {md_escape(key)} | {distinct} | {rendered} |")
        print()
        print(f"Keys with 1–50 distinct non-empty values: **{low}**.")
        print()

        print("## D. Group code integrity")
        print()
        hg_ok = hg_bad = ug_ok = ug_bad = 0
        hg_bad_freq: Counter[str] = Counter()
        ug_bad_freq: Counter[str] = Counter()
        snapshot_hg: Counter[str] = Counter()
        for row in rows:
            hg = row.hauptgruppe_code or ""
            ug = row.untergruppe_code or ""
            snapshot_hg[hg] += 1
            if CODE_RE.match(hg):
                hg_ok += 1
            else:
                hg_bad += 1
                hg_bad_freq[hg] += 1
            if CODE_RE.match(ug):
                ug_ok += 1
            else:
                ug_bad += 1
                ug_bad_freq[ug] += 1

        print("| metric | count |")
        print("|---|---:|")
        print(f"| hauptgruppe_code matches `^[0-9]{{3}}$` | {hg_ok} |")
        print(f"| hauptgruppe_code does not match | {hg_bad} |")
        print(f"| untergruppe_code matches `^[0-9]{{3}}$` | {ug_ok} |")
        print(f"| untergruppe_code does not match | {ug_bad} |")
        print()

        print("### D. Non-matching hauptgruppe_code (top 20)")
        print()
        print("| hauptgruppe_code | rows |")
        print("|---|---:|")
        if hg_bad_freq:
            for value, count in hg_bad_freq.most_common(20):
                print(f"| {md_escape(value)} | {count} |")
        else:
            print("| *(none)* | 0 |")
        print()

        print("### D. Non-matching untergruppe_code (top 20)")
        print()
        print("| untergruppe_code | rows |")
        print("|---|---:|")
        if ug_bad_freq:
            for value, count in ug_bad_freq.most_common(20):
                print(f"| {md_escape(value)} | {count} |")
        else:
            print("| *(none)* | 0 |")
        print()

        registry = list(
            db.scalars(select(Hauptgruppe).where(Hauptgruppe.deleted_at.is_(None)))
        )
        registry_codes = {g.code for g in registry}
        snapshot_codes = {code for code in snapshot_hg if CODE_RE.match(code)}
        missing_in_registry = sorted(snapshot_codes - registry_codes)
        unused_registry = sorted(
            code for code in registry_codes if snapshot_hg.get(code, 0) == 0
        )

        print("### D. Snapshot Hauptgruppe codes with no active registry match")
        print()
        print(f"Count: **{len(missing_in_registry)}**")
        print()
        print("| code | snapshot rows |")
        print("|---|---:|")
        if missing_in_registry:
            for code in missing_in_registry:
                print(f"| {code} | {snapshot_hg[code]} |")
        else:
            print("| *(none)* | 0 |")
        print()

        print("### D. Active registry Hauptgruppen with zero snapshot rows")
        print()
        print(f"Count: **{len(unused_registry)}**")
        print()
        print("| code | name |")
        print("|---|---|")
        if unused_registry:
            by_code = {g.code: g.name for g in registry}
            for code in unused_registry:
                print(f"| {code} | {md_escape(by_code[code])} |")
        else:
            print("| *(none)* | |")
        print()

        print("## E. Emptiness semantics")
        print()
        print(
            "| key | present | empty string | absent | non-empty | "
            "empty-string share of present | absent share of rows |"
        )
        print("|---|---:|---:|---:|---:|---:|---:|")
        for key in sorted(all_keys):
            absent = n_rows - present[key]
            share_empty = (empty_string[key] / present[key]) if present[key] else 0.0
            share_absent = absent / n_rows if n_rows else 0.0
            print(
                f"| {md_escape(key)} | {present[key]} | {empty_string[key]} | "
                f"{absent} | {nonempty[key]} | {share_empty:.1%} | {share_absent:.1%} |"
            )
        print()

        print("## F. Volume and cost")
        print()
        print(f"Row count of current snapshot: **{n_rows}** (header `row_count`={snapshot.row_count}).")
        print()

        timed_key = "Einheit" if "Einheit" in all_keys else sorted(all_keys)[0]
        sid = str(snapshot.id)
        queries = [
            (
                f"seq scan data->>'{timed_key}'",
                text(
                    "SELECT data ->> :key FROM article_snapshot_rows "
                    "WHERE snapshot_id = :sid"
                ),
                {"key": timed_key, "sid": sid},
            ),
            (
                "DISTINCT data->>'Einheit'",
                text(
                    "SELECT DISTINCT data ->> 'Einheit' FROM article_snapshot_rows "
                    "WHERE snapshot_id = :sid"
                ),
                {"sid": sid},
            ),
            (
                "COUNT LIKE on article_name",
                text(
                    "SELECT COUNT(*) FROM article_snapshot_rows "
                    "WHERE snapshot_id = :sid AND article_name LIKE :pat"
                ),
                {"sid": sid, "pat": "%holz%"},
            ),
        ]
        print("| query | ms | rows returned |")
        print("|---|---:|---:|")
        bind = db.connection()
        for label, stmt, params in queries:
            t0 = time.perf_counter()
            result = bind.execute(stmt, params)
            fetched = result.fetchall()
            ms = (time.perf_counter() - t0) * 1000
            print(f"| {label} | {ms:.1f} | {len(fetched)} |")
        print()

        print("## G. Snapshot columns header")
        print()
        header_cols = snapshot.columns or []
        header_keys: list[str] = []
        print("| # | key | title | width |")
        print("|---:|---|---|---:|")
        for i, col in enumerate(header_cols, start=1):
            if not isinstance(col, dict):
                print(f"| {i} | {md_escape(col)} | | |")
                continue
            key = str(col.get("key", ""))
            header_keys.append(key)
            print(
                f"| {i} | {md_escape(key)} | {md_escape(col.get('title', ''))} | "
                f"{col.get('width', '')} |"
            )
        print()
        header_set = set(header_keys)
        only_header = sorted(header_set - all_keys)
        only_union = sorted(all_keys - header_set)
        print(f"Header key count: **{len(header_keys)}** (unique **{len(header_set)}**).")
        print(f"Union key count: **{len(all_keys)}**.")
        print()
        print("| only in `ArticleSnapshot.columns` | only in row `data` union |")
        print("|---|---|")
        if not only_header and not only_union:
            print("| *(none)* | *(none)* |")
        else:
            n = max(len(only_header), len(only_union), 1)
            for i in range(n):
                left = only_header[i] if i < len(only_header) else ""
                right = only_union[i] if i < len(only_union) else ""
                print(f"| {md_escape(left) if left else ''} | {md_escape(right) if right else ''} |")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
