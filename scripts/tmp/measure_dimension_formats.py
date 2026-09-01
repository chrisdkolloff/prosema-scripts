"""Throwaway: measure Breite/Höhe/Länge JSONB shapes on the current snapshot.

Run from the repo root:

    PYTHONPATH=. python scripts/tmp/measure_dimension_formats.py
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import ArticleSnapshot, ArticleSnapshotRow

KEYS = ("Breite in mm", "Höhe in mm", "Länge in cm")

RE_INTEGER = re.compile(r"^[+-]?\d+$")
RE_COMMA_DECIMAL = re.compile(r"^[+-]?\d+,\d+$")
RE_DOT_NUMBER = re.compile(r"^[+-]?\d+\.\d+$")
RE_APOSTROPHE = re.compile(r"^[+-]?\d{1,3}(?:'\d{3})+(?:[.,]\d+)?$")

BUCKETS = (
    "plain integer",
    "dot decimal",
    "comma decimal",
    "dot thousands",
    "apostrophe thousands",
    "anything else",
)

# Decimal conventions (integer is format-agnostic).
DECIMAL_BUCKETS = frozenset(
    {"dot decimal", "comma decimal", "dot thousands", "apostrophe thousands"}
)


def classify(value: str) -> str:
    raw = value.strip()
    if RE_APOSTROPHE.match(raw):
        return "apostrophe thousands"
    if RE_COMMA_DECIMAL.match(raw):
        return "comma decimal"
    matched = RE_DOT_NUMBER.match(raw)
    if matched:
        after_dot = raw.rsplit(".", 1)[1]
        if after_dot.lstrip("+-") and len(after_dot) == 3 and after_dot.isdigit():
            return "dot thousands"
        return "dot decimal"
    if RE_INTEGER.match(raw):
        return "plain integer"
    return "anything else"


def parse_comma(raw: str) -> Decimal:
    return Decimal(raw.replace(",", "."))


def parse_dot(raw: str) -> Decimal:
    return Decimal(raw)


def dominant_format(counts: Counter[str]) -> str | None:
    comma = counts["comma decimal"]
    dot = counts["dot decimal"] + counts["dot thousands"]
    apostrophe = counts["apostrophe thousands"]
    scored = [("comma", comma), ("dot", dot), ("apostrophe", apostrophe)]
    scored.sort(key=lambda item: item[1], reverse=True)
    if scored[0][1] == 0:
        if counts["plain integer"]:
            return "integer"
        return None
    return scored[0][0]


def min_max(values: list[tuple[str, str]], fmt: str | None) -> tuple[Decimal | None, Decimal | None, int]:
    parsed: list[Decimal] = []
    for raw, bucket in values:
        try:
            if fmt == "comma":
                if bucket in ("plain integer", "comma decimal"):
                    parsed.append(parse_comma(raw))
            elif fmt == "dot":
                if bucket in ("plain integer", "dot decimal", "dot thousands"):
                    parsed.append(parse_dot(raw))
            elif fmt == "integer":
                if bucket == "plain integer":
                    parsed.append(Decimal(raw))
            elif fmt == "apostrophe":
                if bucket in ("plain integer", "apostrophe thousands"):
                    cleaned = raw.replace("'", "")
                    if "," in cleaned:
                        cleaned = cleaned.replace(",", ".")
                    parsed.append(Decimal(cleaned))
        except InvalidOperation:
            continue
    if not parsed:
        return None, None, 0
    return min(parsed), max(parsed), len(parsed)


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

        rows = list(
            db.scalars(
                select(ArticleSnapshotRow).where(
                    ArticleSnapshotRow.snapshot_id == snapshot.id
                )
            )
        )
        n_rows = len(rows)

        print("# Dimension column format measurement")
        print()
        print(f"- **id:** `{snapshot.id}`")
        print(f"- **created_at:** `{snapshot.created_at.isoformat()}`")
        print(f"- **row_count header:** {snapshot.row_count}")
        print(f"- **rows loaded:** {n_rows}")
        print(f"- **weclapp_tenant:** `{snapshot.weclapp_tenant}`")
        print()

        mixed = False
        anything_else = False

        for key in KEYS:
            present = 0
            nonempty = 0
            counts: Counter[str] = Counter()
            classified: list[tuple[str, str]] = []
            else_examples: list[str] = []
            bucket_examples: dict[str, list[str]] = {b: [] for b in BUCKETS}
            for row in rows:
                data = row.data if isinstance(row.data, dict) else {}
                if key not in data:
                    continue
                present += 1
                raw = data[key]
                text_value = "" if raw is None else str(raw)
                if text_value.strip() == "":
                    continue
                nonempty += 1
                bucket = classify(text_value)
                counts[bucket] += 1
                classified.append((text_value, bucket))
                samples = bucket_examples[bucket]
                if text_value not in samples and len(samples) < 10:
                    samples.append(text_value)
                if (
                    bucket == "anything else"
                    and text_value not in else_examples
                    and len(else_examples) < 10
                ):
                    else_examples.append(text_value)

            decimal_present = [b for b in DECIMAL_BUCKETS if counts[b]]
            # comma vs (dot decimal ∪ 1.234 form) vs apostrophe
            conventions = []
            if counts["comma decimal"]:
                conventions.append("comma")
            if counts["dot decimal"] or counts["dot thousands"]:
                conventions.append("dot")
            if counts["apostrophe thousands"]:
                conventions.append("apostrophe")
            fmt = dominant_format(counts)
            lo, hi, n_parsed = min_max(classified, fmt)

            if len(conventions) > 1:
                mixed = True
            if counts["anything else"]:
                anything_else = True

            print(f"## {key}")
            print()
            print("| metric | count |")
            print("|---|---:|")
            print(f"| total rows | {n_rows} |")
            print(f"| rows with key | {present} |")
            print(f"| rows with non-empty value | {nonempty} |")
            print()
            print("| shape | count |")
            print("|---|---:|")
            for bucket in BUCKETS:
                print(f"| {bucket} | {counts[bucket]} |")
            leftover = nonempty - sum(counts[b] for b in BUCKETS)
            if leftover:
                print(f"| (unbucketed — bug) | {leftover} |")
            print()
            print("Anything-else examples (up to 10, verbatim):")
            print()
            if else_examples:
                for i, example in enumerate(else_examples, start=1):
                    print(f"{i}. `{example}`")
            else:
                print("*(none)*")
            print()
            print(f"- decimal conventions present: {conventions or ['(none — integers only)']}")
            print(f"- 1.234-form (dot, exactly three digits after): {counts['dot thousands']}")
            print(f"- dominant interpretation: `{fmt}`")
            print(f"- min: `{lo}`")
            print(f"- max: `{hi}`")
            print(f"- values included in min/max: {n_parsed}")
            print()
            for bucket in ("comma decimal", "dot decimal", "dot thousands", "apostrophe thousands"):
                if not counts[bucket]:
                    continue
                freq = Counter(raw for raw, b in classified if b == bucket)
                print(
                    f"`{bucket}`: {counts[bucket]} values, {len(freq)} distinct. "
                    "All distinct (value × count):"
                )
                print()
                for value, n in freq.most_common():
                    print(f"- `{value}` × {n}")
                print()

        print("## Gate")
        print()
        print(f"- more than one decimal convention on any column: **{mixed}**")
        print(f"- any anything-else values: **{anything_else}**")
        if mixed or anything_else:
            print("- **STOP:** do not update the catalogue.")
        else:
            print("- measurement is clean enough to proceed after confirmation.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
