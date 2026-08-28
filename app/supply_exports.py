"""Bezugsquellenexport: pull, edit, validate, diff."""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import DiscountCategory, ExportRow, ExportRun, UserPreference
from app.supply_export_fields import (
    BY_KEY,
    FIELDS,
    PICKER_GROUPS,
    PRESET_ALL,
    PRESET_MANDATORY,
    PRESET_STANDARD,
    TOOL_KEY,
    FieldSpec,
    default_visible_keys,
    editable_keys,
    freeze_column_count,
    grid_field_order,
    picker_fields,
    preset_keys,
    resolve_visible_keys,
)
from scripts.weclapp.master_columns import (
    _custom_attributes_by_label,
    _first_price,
    _format_decimal,
    _format_ean,
    _format_weclapp_timestamp,
    build_lookups,
    strip_html,
)

logger = logging.getLogger(__name__)

ZURICH = ZoneInfo("Europe/Zurich")
GRID_PAGE_SIZE = 250
FLUSH_IDLE_MS = 400
DEFAULT_SUPPLIER_ID = "10000"
DEFAULT_MARKUP = Decimal("50")
DEFAULT_EUR_CHF = Decimal("0.9300")
SALES_CURRENCIES = ("EUR", "CHF")
DEFAULT_SALES_CURRENCY = "EUR"

# Canonical PROSEMA form is MMM.SSS.NNNN (4-digit running). Live data also has
# a 3-digit running part (e.g. 060.010.800, 999.999.001).
PROSEMA_ARTICLE_NUMBER_RE = re.compile(r"^\d{3}\.\d{3}\.\d{3,4}$")

JSPREADSHEET_CE_VERSION = "5.0.4"
JSUITES_VERSION = "5.13.5"

INCLUDE_FIELD = "included"  # internal dirty flag for non-price edits; not shown in grid
ARTICLE_NUMBER_FIELD = "article_number"
SUPPLIER_ARTICLE_FIELD = "supplier_article_number"
SUPPLIER_NUMBER_FIELD = "supplier_number"
ZERO_CATEGORY_LABEL = "— kein Rabatt —"

SYNTHETIC_FIELDS = ("_status", "ek_after", "sale_chf")
EDITABLE_WHITELIST = editable_keys()
GRID_FIELD_ORDER: tuple[str, ...] = grid_field_order()
JA_NEIN_TRUE = frozenset({"ja", "true", "1", "yes", "on"})
JA_NEIN_FALSE = frozenset({"nein", "false", "0", "no", "off"})


def is_prosema_article_number(value: str) -> bool:
    return bool(PROSEMA_ARTICLE_NUMBER_RE.fullmatch((value or "").strip()))


def article_number_column_width(article_numbers: list[str]) -> int:
    """Fit the longest Artikelnummer (monospace-ish), ignore short header."""
    samples = [n for n in article_numbers if n]
    longest = max(samples, key=len) if samples else "000.000.0000"
    # ~9px per character + padding; clamp for the usual XXX.XXX.XXXX form
    return max(110, min(200, int(len(longest) * 9) + 24))


_LABEL_RE = re.compile(r"^(.*?)\s*-\s*(\d{3})\s*$")


@dataclass
class ExportFilters:
    query: str = ""
    discount_category: str = ""  # "" = all, "__none__" = empty, "__zero__" = explicit zero
    hauptgruppe: str = ""
    untergruppe: str = ""
    changed_only: bool = False
    unresolved_only: bool = False
    page: int = 1


@dataclass
class ValidationIssue:
    level: str  # 'error' | 'warning'
    code: str
    message: str
    row_id: uuid.UUID | None = None
    article_number: str = ""
    supplier_article_number: str = ""


@dataclass
class DiffEntry:
    kind: str
    supplier_article_number: str
    article_number: str = ""
    field: str = ""
    old_value: str = ""
    new_value: str = ""


@dataclass
class WrittenColumn:
    field_key: str
    label: str
    weclapp_column: str
    non_empty_count: int


@dataclass
class PreviewReport:
    included_count: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    explicit_zero_count: int = 0
    ek_before_sum: Decimal = Decimal("0")
    ek_after_sum: Decimal = Decimal("0")
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    weclapp_diff: list[DiffEntry] = field(default_factory=list)
    prior_run_diff: list[DiffEntry] = field(default_factory=list)
    skipped_no_supply_source: list[str] = field(default_factory=list)
    written_columns: list[WrittenColumn] = field(default_factory=list)


def format_swiss_number(value: int) -> str:
    return f"{value:,}".replace(",", "\u202f")


def format_run_timestamp(when: datetime) -> str:
    local = when.astimezone(ZURICH)
    return local.strftime("%d.%m.%Y, %H:%M Uhr")


def format_iso_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def format_display_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def parse_iso_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Preis-Eintritt muss ein gültiges Datum sein.") from exc


def filename_timestamp(when: datetime) -> str:
    local = when.astimezone(ZURICH)
    return local.strftime("%Y-%m-%d_%H%M")


def _parse_decimal(raw: object) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, Decimal):
        return raw
    text = str(raw).strip().replace("'", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_ja_nein(raw: object) -> bool | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().casefold()
    if text in JA_NEIN_TRUE:
        return True
    if text in JA_NEIN_FALSE:
        return False
    return None


def _fmt_ja_nein(value: bool | None) -> str:
    if value is None:
        return ""
    return "ja" if value else "nein"


def _parse_date_cell(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    raise ValueError(f"Ungültiges Datum: {text}")


def extras_dict(row: ExportRow) -> dict[str, Any]:
    data = row.extras if isinstance(row.extras, dict) else {}
    return dict(data)


def article_context_dict(row: ExportRow) -> dict[str, Any]:
    data = row.article_context if isinstance(row.article_context, dict) else {}
    return dict(data)


def stored_field_text(row: ExportRow, spec: FieldSpec) -> str:
    if spec.store == "extras":
        value = extras_dict(row).get(spec.field_key, "")
        return "" if value is None else str(value)
    if spec.store == "article_context":
        value = article_context_dict(row).get(spec.field_key, "")
        return "" if value is None else str(value)
    if spec.store == "row":
        value = getattr(row, spec.row_attr, None)
        if spec.input_kind == "ja_nein":
            return _fmt_ja_nein(value if isinstance(value, bool) else None)
        if isinstance(value, bool):
            return _fmt_ja_nein(value)
        return _fmt_cell(value)
    return ""


def extras_has_writes(row: ExportRow) -> bool:
    extras = extras_dict(row)
    for key, value in extras.items():
        spec = BY_KEY.get(str(key))
        if spec is None:
            continue
        if spec.write_policy == "on_value" and spec.store == "extras" and str(value or "").strip():
            return True
    return False


def locked_extras_keys(row: ExportRow) -> list[str]:
    extras = extras_dict(row)
    found: list[str] = []
    for key, value in extras.items():
        if not str(value or "").strip():
            continue
        spec = BY_KEY.get(str(key))
        if spec is None or spec.write_policy == "locked":
            found.append(str(key))
        elif spec.store != "extras" or spec.edit_policy != "editable":
            found.append(str(key))
    return found


def normalize_extra_value(spec: FieldSpec, raw: object) -> str:
    if spec.input_kind == "ja_nein":
        parsed = _parse_ja_nein(raw)
        return _fmt_ja_nein(parsed) if parsed is not None else ""
    if spec.input_kind in {"numeric", "percent"}:
        parsed = _parse_decimal(raw)
        if parsed is None:
            if str(raw or "").strip():
                raise ValueError(f"{spec.label_internal} ist keine Zahl")
            return ""
        return str(parsed)
    if spec.input_kind == "date":
        return _parse_date_cell(raw)
    return str(raw or "").strip()


def _as_bool_flag(value: object) -> bool:
    parsed = _parse_ja_nein(value)
    if parsed is not None:
        return parsed
    return bool(value)


def _dropshipping_from_supply(supply: dict[str, Any]) -> bool:
    for key in ("dropShippingPossible", "dropshippingPossible", "dropShipping"):
        if key in supply and supply[key] not in (None, ""):
            return _as_bool_flag(supply[key])
    return False


def freeze_article_context(
    article: dict[str, Any],
    lookups: Any,
) -> dict[str, str]:
    ctx: dict[str, str] = {}
    ctx["local_article_name"] = str(
        article.get("localizedName") or article.get("shortName") or ""
    ).strip()
    ctx["trade_language"] = str(article.get("language") or "").strip()
    ctx["short_text_1"] = str(article.get("shortDescription1") or "").strip()
    ctx["short_text_2"] = str(article.get("shortDescription2") or "").strip()
    ctx["article_description"] = strip_html(article.get("description") or "")
    ctx["internal_note"] = strip_html(article.get("internalNote") or "")
    ctx["long_description"] = strip_html(article.get("longText") or "")
    ctx["ean"] = _format_ean(article.get("ean"))
    ctx["mpn"] = str(
        article.get("manufacturerPartNumber") or article.get("mpn") or ""
    ).strip()
    ctx["manufacturer"] = str(
        article.get("manufacturerName") or article.get("manufacturer") or ""
    ).strip()
    ctx["gross_weight"] = _format_decimal(article.get("articleGrossWeight"))
    ctx["net_weight"] = _format_decimal(article.get("articleNetWeight"))
    tariff = lookups.customs_tariff_name(str(article.get("customsTariffNumberId") or ""))
    ctx["customs_tariff"] = tariff if isinstance(tariff, str) else ""
    ctx["article_length"] = _format_decimal(article.get("articleLength"))
    ctx["article_width"] = _format_decimal(article.get("articleWidth"))
    ctx["article_height"] = _format_decimal(article.get("articleHeight"))
    ctx["manufacturer_type"] = str(article.get("manufacturerType") or "").strip()
    launch = article.get("launchDate") or article.get("introductionDate")
    if launch not in (None, ""):
        stamp = _format_weclapp_timestamp(launch)
        ctx["launch_date"] = stamp.split(" ")[0] if stamp else ""
    return {key: value for key, value in ctx.items() if value}


def load_visible_fields(db: Session, user_oid: str) -> list[str]:
    pref = db.get(UserPreference, {"user_oid": user_oid, "tool_key": TOOL_KEY})
    stored: list[str] | None = None
    if pref is not None:
        raw = (pref.pref_json or {}).get("visible")
        if isinstance(raw, list):
            stored = [str(item) for item in raw]
    return resolve_visible_keys(stored)


def save_visible_fields(
    db: Session,
    user_oid: str,
    *,
    visible: list[str] | None = None,
    preset: str | None = None,
) -> list[str]:
    if preset:
        keys = list(preset_keys(preset))
    else:
        keys = resolve_visible_keys(visible)
    pref = db.get(UserPreference, {"user_oid": user_oid, "tool_key": TOOL_KEY})
    payload = {"visible": keys}
    if preset:
        payload["preset"] = preset
    now = datetime.now(tz=ZURICH)
    if pref is None:
        pref = UserPreference(
            user_oid=user_oid,
            tool_key=TOOL_KEY,
            pref_json=payload,
            updated_at=now,
        )
        db.add(pref)
    else:
        pref.pref_json = payload
        pref.updated_at = now
    return keys


def picker_payload(visible: list[str]) -> dict[str, Any]:
    visible_set = set(visible)
    groups: list[dict[str, Any]] = []
    for group_id, label, hint in PICKER_GROUPS:
        entries: list[dict[str, Any]] = []
        for spec in picker_fields():
            if spec.picker_group != group_id:
                continue
            entries.append(
                {
                    "field_key": spec.field_key,
                    "label": spec.label_internal,
                    "weclapp_column": spec.weclapp_column,
                    "note": spec.note,
                    "read_only": spec.edit_policy != "editable",
                    "hideable": spec.hideable,
                    "checked": spec.field_key in visible_set,
                }
            )
        groups.append(
            {
                "id": group_id,
                "label": label,
                "hint": hint,
                "collapsed": group_id in {"optional", "article"},
                "entries": entries,
            }
        )
    return {
        "groups": groups,
        "presets": [
            {"id": PRESET_STANDARD, "label": "Standard"},
            {"id": PRESET_MANDATORY, "label": "Nur Pflicht"},
            {"id": PRESET_ALL, "label": "Alles"},
        ],
        "visible": visible,
    }


def _active_supply_price(prices: object) -> dict[str, Any] | None:
    """Pick the current articlePrices entry (no endDate, else latest startDate)."""
    if not isinstance(prices, list):
        return None
    open_prices: list[dict[str, Any]] = []
    closed_prices: list[dict[str, Any]] = []
    for entry in prices:
        if not isinstance(entry, dict) or entry.get("price") is None:
            continue
        if entry.get("endDate") in (None, ""):
            open_prices.append(entry)
        else:
            closed_prices.append(entry)
    pool = open_prices or closed_prices
    if not pool:
        return None
    return max(pool, key=lambda p: int(p.get("startDate") or 0))


def _price_and_reductions(
    prices: object,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """EK + first two REDUCTION_PERCENT values from the active supply price."""
    entry = _active_supply_price(prices)
    if entry is None:
        return None, None, None
    ek = _parse_decimal(entry.get("price"))
    reductions: list[Decimal] = []
    for red in entry.get("reductionAdditions") or []:
        if not isinstance(red, dict):
            continue
        if str(red.get("type") or "") != "REDUCTION_PERCENT":
            continue
        parsed = _parse_decimal(red.get("value"))
        if parsed is not None:
            reductions.append(parsed)
    d1 = reductions[0] if len(reductions) > 0 else None
    d2 = reductions[1] if len(reductions) > 1 else None
    return ek, d1, d2


def _group_code(label: str) -> str:
    match = _LABEL_RE.match((label or "").strip())
    return match.group(2) if match else ""


def ek_after_discount(
    ek: Decimal | None,
    d1: Decimal,
    d2: Decimal,
) -> Decimal | None:
    if ek is None:
        return None
    return (ek * (1 - d1 / 100) * (1 - d2 / 100)).quantize(Decimal("0.01"))


def sale_price_chf(
    ek_after: Decimal | None,
    markup_pct: Decimal,
    eur_chf_rate: Decimal,
) -> Decimal | None:
    if ek_after is None:
        return None
    return (ek_after * (1 + markup_pct / 100) * eur_chf_rate).quantize(Decimal("0.01"))


def current_discount_categories(
    db: Session,
    supplier_id: str,
    *,
    on_date: date | None = None,
) -> dict[str, DiscountCategory]:
    on_date = on_date or date.today()
    rows = db.scalars(
        select(DiscountCategory).where(
            DiscountCategory.supplier_id == supplier_id,
            DiscountCategory.valid_from <= on_date,
            or_(
                DiscountCategory.valid_to.is_(None),
                DiscountCategory.valid_to >= on_date,
            ),
        )
    ).all()
    # Prefer open (valid_to IS NULL) rows; otherwise latest valid_from.
    by_code: dict[str, DiscountCategory] = {}
    for row in rows:
        existing = by_code.get(row.category_code)
        if existing is None:
            by_code[row.category_code] = row
            continue
        if existing.valid_to is not None and row.valid_to is None:
            by_code[row.category_code] = row
        elif row.valid_from > existing.valid_from and (
            row.valid_to is None or existing.valid_to is not None
        ):
            by_code[row.category_code] = row
    return by_code


def is_override(row: ExportRow, registry: DiscountCategory | None) -> bool:
    if row.discount_intent != "apply" or registry is None:
        return False
    return (
        Decimal(row.base_discount_pct) != Decimal(registry.base_discount_pct)
        or Decimal(row.customer_discount_pct) != Decimal(registry.customer_discount_pct)
    )


def _dec_ne(left: Decimal | None, right: Decimal | None) -> bool:
    if left is None and right is None:
        return False
    if left is None or right is None:
        return True
    return Decimal(left) != Decimal(right)


def export_discount_values(row: ExportRow) -> tuple[Decimal, Decimal]:
    if row.discount_intent == "zero":
        return Decimal("0"), Decimal("0")
    return Decimal(row.base_discount_pct), Decimal(row.customer_discount_pct)


def row_has_changes(row: ExportRow) -> bool:
    """True if exporting this row would change something in weclapp (or a non-price edit)."""
    # Dirty flag for non-price edits (matchcode/primary/dropshipping/extras).
    if row.included:
        return True
    if extras_has_writes(row):
        return True
    if row.dropshipping_possible != row.weclapp_current_dropshipping:
        return True
    # Unresolved rows cannot be serialised; leave weclapp alone unless marked dirty above.
    if row.discount_intent == "unresolved":
        return False
    if _dec_ne(row.ek_price_before_discount, row.weclapp_current_ek):
        return True
    d1, d2 = export_discount_values(row)
    cur_d1 = row.weclapp_current_base_discount_pct
    cur_d2 = row.weclapp_current_customer_discount_pct
    if cur_d1 is None and cur_d2 is None:
        # No discount readable in weclapp: writing explicit zeros is a no-op; rates are a change.
        return row.discount_intent == "apply" and (d1 != 0 or d2 != 0)
    return _dec_ne(d1, cur_d1) or _dec_ne(d2, cur_d2)


def row_is_highlighted(
    row: ExportRow,
    registry: dict[str, DiscountCategory],
) -> bool:
    """Yellow highlight: user-touched or rate override — not every weclapp diff."""
    return bool(row.included) or is_override(row, registry.get(row.discount_category))


def running_export(db: Session) -> ExportRun | None:
    return db.scalars(
        select(ExportRun).where(ExportRun.status == "running").limit(1)
    ).first()


def list_exports(db: Session, *, supplier_id: str | None = None) -> list[ExportRun]:
    stmt = select(ExportRun).order_by(ExportRun.created_at.desc())
    if supplier_id:
        stmt = stmt.where(ExportRun.supplier_id == supplier_id)
    return list(db.scalars(stmt))


def previous_exported_run(
    db: Session,
    *,
    supplier_id: str,
    before: ExportRun,
) -> ExportRun | None:
    return db.scalars(
        select(ExportRun)
        .where(
            ExportRun.supplier_id == supplier_id,
            ExportRun.status == "exported",
            ExportRun.created_at < before.created_at,
            ExportRun.id != before.id,
        )
        .order_by(ExportRun.created_at.desc())
        .limit(1)
    ).first()


def create_export_pull(
    db: Session,
    user: dict[str, Any],
    *,
    supplier_id: str = DEFAULT_SUPPLIER_ID,
) -> ExportRun:
    from app.jobs import enqueue

    if running_export(db) is not None:
        raise ValueError("Es läuft bereits eine Abfrage.")

    run = ExportRun(
        id=uuid.uuid4(),
        status="running",
        created_by_oid=str(user["oid"]),
        created_by_name=str(user.get("name") or ""),
        supplier_id=supplier_id.strip(),
        markup_pct=DEFAULT_MARKUP,
        eur_chf_rate=DEFAULT_EUR_CHF,
        eur_chf_rate_date=date.today(),
        price_entry_date=None,
        sales_article_currency=DEFAULT_SALES_CURRENCY,
        filter_json={"supplier_id": supplier_id.strip()},
    )
    db.add(run)
    db.flush()
    job = enqueue(
        db,
        "weclapp_supply_source_export",
        {"export_run_id": str(run.id)},
        user,
    )
    run.job_id = job.id
    db.commit()
    db.refresh(run)
    return run


def fail_export(db: Session, run: ExportRun, message: str) -> None:
    run.status = "failed"
    run.error = message
    db.commit()


def _article_supply_source_ids(article: dict[str, Any]) -> set[str]:
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


def _resolve_discount(
    category_code: str,
    registry: dict[str, DiscountCategory],
) -> tuple[str, Decimal, Decimal, int | None]:
    code = (category_code or "").strip()
    if not code:
        return "unresolved", Decimal("0"), Decimal("0"), None
    cat = registry.get(code)
    if cat is None:
        return "unresolved", Decimal("0"), Decimal("0"), None
    return (
        "apply",
        Decimal(cat.base_discount_pct),
        Decimal(cat.customer_discount_pct),
        cat.id,
    )


def pull_export_rows(db: Session, run: ExportRun, *, oid: str) -> dict[str, Any]:
    """Fetch articles + supply sources and materialise update rows for one supplier."""
    from app.weclapp import weclapp_client_for

    client = weclapp_client_for(db, oid)
    articles = list(client.iter_pages("article"))
    lookups = build_lookups(client, articles)
    registry = current_discount_categories(db, run.supplier_id)

    ss_to_articles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    articles_without_any_ss: list[str] = []
    articles_without_supplier_ss: list[str] = []

    for article in articles:
        ss_ids = _article_supply_source_ids(article)
        article_number = str(article.get("articleNumber") or "").strip()
        if not ss_ids:
            if article_number:
                articles_without_any_ss.append(article_number)
            continue
        linked_to_supplier = False
        for sid in ss_ids:
            ss_to_articles[sid].append(article)
            supply = lookups.supply_source(sid)
            party = lookups.party(str(supply.get("supplierId") or ""))
            if str(party.get("supplierNumber") or "") == run.supplier_id:
                linked_to_supplier = True
        if not linked_to_supplier and article_number:
            articles_without_supplier_ss.append(article_number)

    db.execute(delete(ExportRow).where(ExportRow.run_id == run.id))

    position = 0
    seen_keys: set[tuple[str, str]] = set()
    orphan_supply_sources: list[str] = []

    for ss_id, supply in lookups.supply_sources.items():
        party = lookups.party(str(supply.get("supplierId") or ""))
        supplier_number = str(party.get("supplierNumber") or "").strip()
        if supplier_number != run.supplier_id:
            continue

        supplier_article_number = str(supply.get("articleNumber") or "").strip()
        linked_articles = ss_to_articles.get(ss_id, [])
        if not linked_articles:
            orphan_supply_sources.append(ss_id)
            continue

        ek, cur_d1, cur_d2 = _price_and_reductions(supply.get("articlePrices"))
        if ek is None:
            ek = _parse_decimal(_first_price(supply.get("articlePrices")))
        dropshipping = _dropshipping_from_supply(supply)

        # One row per linked sales article. A shared supply source under two
        # article numbers must surface as two rows so the (D, F) duplicate
        # check can block the run rather than silently picking one.
        for article in linked_articles:
            article_number = str(article.get("articleNumber") or "").strip()
            key = (ss_id, article_number)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            attrs = _custom_attributes_by_label(article, lookups.attribute_labels)
            category_code = str(attrs.get("Rabattcode") or "").strip()
            intent, d1, d2, cat_id = _resolve_discount(category_code, registry)

            haupt, unter = lookups.category_names(
                str(article.get("articleCategoryId") or "")
            )
            unit = lookups.unit_name(
                str(supply.get("unitId") or article.get("unitId") or "")
            )

            db.add(
                ExportRow(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    position=position,
                    article_number=article_number,
                    supplier_article_number=supplier_article_number,
                    supplier_number=supplier_number,
                    article_name=str(article.get("name") or "").strip(),
                    ek_price_before_discount=ek,
                    unit=unit,
                    matchcode=str(article.get("matchCode") or "").strip(),
                    discount_category=category_code,
                    discount_category_id=cat_id,
                    base_discount_pct=d1,
                    customer_discount_pct=d2,
                    discount_intent=intent,
                    row_intent="update",
                    included=False,
                    weclapp_supply_source_id=ss_id,
                    weclapp_current_ek=ek,
                    weclapp_current_base_discount_pct=cur_d1,
                    weclapp_current_customer_discount_pct=cur_d2,
                    weclapp_current_is_primary=str(
                        article.get("primarySupplySourceId") or ""
                    )
                    == ss_id,
                    hauptgruppe_code=_group_code(haupt) or haupt,
                    untergruppe_code=_group_code(unter) or unter,
                    extras={},
                    article_context=freeze_article_context(article, lookups),
                    dropshipping_possible=dropshipping,
                    weclapp_current_dropshipping=dropshipping,
                )
            )
            position += 1

    run.row_count = position
    run.included_count = 0
    run.status = "draft"
    run.error = None
    run.summary_json = {
        "articles_without_any_supply_source": len(articles_without_any_ss),
        "articles_without_supplier_supply_source": len(articles_without_supplier_ss),
        "articles_without_supplier_supply_source_sample": articles_without_supplier_ss[
            :100
        ],
        "orphan_supply_sources": orphan_supply_sources[:50],
        "orphan_supply_source_count": len(orphan_supply_sources),
        "registry_categories": sorted(registry.keys()),
    }
    db.commit()
    return {
        "row_count": position,
        "skipped_no_supplier_ss": len(articles_without_supplier_ss),
        "orphans": len(orphan_supply_sources),
    }


def _base_row_query(run_id: uuid.UUID, filters: ExportFilters):
    stmt = select(ExportRow).where(ExportRow.run_id == run_id)
    if filters.unresolved_only:
        stmt = stmt.where(ExportRow.discount_intent == "unresolved")
    if filters.discount_category == "__none__":
        stmt = stmt.where(
            ExportRow.discount_category == "",
            ExportRow.discount_intent != "zero",
        )
    elif filters.discount_category == "__zero__":
        stmt = stmt.where(ExportRow.discount_intent == "zero")
    elif filters.discount_category:
        stmt = stmt.where(ExportRow.discount_category == filters.discount_category)
    if filters.hauptgruppe:
        stmt = stmt.where(ExportRow.hauptgruppe_code == filters.hauptgruppe)
    if filters.untergruppe:
        stmt = stmt.where(ExportRow.untergruppe_code == filters.untergruppe)
    needle = filters.query.strip().lower()
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                func.lower(ExportRow.article_number).like(pattern),
                func.lower(ExportRow.article_name).like(pattern),
                func.lower(ExportRow.supplier_article_number).like(pattern),
            )
        )
    return stmt


def count_filtered_rows(db: Session, run_id: uuid.UUID, filters: ExportFilters) -> int:
    if not filters.changed_only:
        stmt = select(func.count()).select_from(
            _base_row_query(run_id, filters).subquery()
        )
        return int(db.scalar(stmt) or 0)
    # changed_only needs Python-side check (compares to weclapp_current_*)
    return len(fetch_all_filtered_rows(db, run_id, filters))


def fetch_filtered_rows(
    db: Session,
    run_id: uuid.UUID,
    filters: ExportFilters,
) -> tuple[list[ExportRow], int, int]:
    ordered = _base_row_query(run_id, filters).order_by(ExportRow.position)
    if filters.changed_only:
        matched = [row for row in db.scalars(ordered) if row_has_changes(row)]
        total = len(matched)
        page = max(1, filters.page)
        start = (page - 1) * GRID_PAGE_SIZE
        rows = matched[start : start + GRID_PAGE_SIZE]
        pages = max(1, (total + GRID_PAGE_SIZE - 1) // GRID_PAGE_SIZE) if total else 1
        return rows, total, pages

    total = count_filtered_rows(db, run_id, filters)
    page = max(1, filters.page)
    start = (page - 1) * GRID_PAGE_SIZE
    stmt = ordered.offset(start).limit(GRID_PAGE_SIZE)
    rows = list(db.scalars(stmt))
    pages = max(1, (total + GRID_PAGE_SIZE - 1) // GRID_PAGE_SIZE) if total else 1
    return rows, total, pages


def fetch_all_filtered_rows(
    db: Session,
    run_id: uuid.UUID,
    filters: ExportFilters,
) -> list[ExportRow]:
    ordered = _base_row_query(run_id, filters).order_by(ExportRow.position)
    rows = list(db.scalars(ordered))
    if filters.changed_only:
        return [row for row in rows if row_has_changes(row)]
    return rows


def fetch_all_filtered_row_ids(
    db: Session,
    run_id: uuid.UUID,
    filters: ExportFilters,
) -> list[uuid.UUID]:
    return [row.id for row in fetch_all_filtered_rows(db, run_id, filters)]


def distinct_values(db: Session, run_id: uuid.UUID, column) -> list[str]:
    stmt = (
        select(column)
        .where(ExportRow.run_id == run_id, column != "")
        .distinct()
        .order_by(column)
    )
    return [value for (value,) in db.execute(stmt).all()]


def assert_run_editable(run: ExportRun) -> None:
    if run.status == "exported":
        raise ValueError("Exportierter Lauf ist schreibgeschützt.")
    if run.status not in {"draft"}:
        raise ValueError("Lauf ist nicht bearbeitbar.")


def apply_run_settings(
    run: ExportRun,
    *,
    price_entry_date: date | None,
    sales_article_currency: str,
) -> None:
    assert_run_editable(run)
    currency = (sales_article_currency or "").strip().upper()
    if currency not in SALES_CURRENCIES:
        raise ValueError("Verkaufsartikel-Währung muss EUR oder CHF sein.")
    if price_entry_date is None:
        raise ValueError("Preis-Eintritt ist nicht gesetzt.")
    run.price_entry_date = price_entry_date
    run.sales_article_currency = currency


def apply_row_patch(
    db: Session,
    run: ExportRun,
    row: ExportRow,
    patch: dict[str, Any],
    registry: dict[str, DiscountCategory],
) -> ExportRow:
    assert_run_editable(run)
    dirty = False

    if "discount_category" in patch:
        raw = str(patch["discount_category"] or "").strip()
        if raw in {ZERO_CATEGORY_LABEL, "__zero__"}:
            row.discount_intent = "zero"
            row.discount_category = ""
            row.discount_category_id = None
            row.base_discount_pct = Decimal("0")
            row.customer_discount_pct = Decimal("0")
        else:
            row.discount_category = raw
            intent, d1, d2, cat_id = _resolve_discount(raw, registry)
            row.discount_intent = intent
            row.base_discount_pct = d1
            row.customer_discount_pct = d2
            row.discount_category_id = cat_id

    if "ek_price_before_discount" in patch:
        row.ek_price_before_discount = _parse_decimal(patch["ek_price_before_discount"])

    if "base_discount_pct" in patch and row.discount_intent != "zero":
        parsed = _parse_decimal(patch["base_discount_pct"])
        if parsed is not None:
            row.base_discount_pct = parsed
            if row.discount_intent == "unresolved":
                row.discount_intent = "apply"

    if "customer_discount_pct" in patch and row.discount_intent != "zero":
        parsed = _parse_decimal(patch["customer_discount_pct"])
        if parsed is not None:
            row.customer_discount_pct = parsed
            if row.discount_intent == "unresolved":
                row.discount_intent = "apply"

    if "override_reason" in patch:
        reason = str(patch["override_reason"] or "").strip()
        row.override_reason = reason or None

    if "matchcode" in patch:
        row.matchcode = str(patch["matchcode"] or "").strip()
        dirty = True

    if "is_primary" in patch or "weclapp_current_is_primary" in patch:
        raw = patch["is_primary"] if "is_primary" in patch else patch["weclapp_current_is_primary"]
        parsed = _parse_ja_nein(raw)
        row.weclapp_current_is_primary = bool(parsed) if parsed is not None else bool(raw)
        dirty = True

    if "dropshipping_possible" in patch:
        parsed = _parse_ja_nein(patch["dropshipping_possible"])
        if parsed is None:
            raise ValueError("Dropshipping möglich: ja oder nein")
        row.dropshipping_possible = parsed
        dirty = True

    extras_patch = False
    extras = extras_dict(row)
    for field_key, raw in patch.items():
        spec = BY_KEY.get(field_key)
        if spec is None or spec.store != "extras":
            continue
        if spec.edit_policy != "editable":
            raise ValueError(f"Feld nicht bearbeitbar: {field_key}")
        normalized = normalize_extra_value(spec, raw)
        if normalized:
            extras[field_key] = normalized
        else:
            extras.pop(field_key, None)
        extras_patch = True
    if extras_patch:
        row.extras = extras
        dirty = True

    if dirty:
        row.included = True

    return row


def row_status_label(
    row: ExportRow,
    registry: dict[str, DiscountCategory],
) -> str:
    parts: list[str] = []
    if row_has_changes(row):
        parts.append("Änderung")
    if row.discount_intent == "unresolved":
        parts.append("ungeklärt")
    elif row.discount_intent == "zero":
        parts.append("kein Rabatt")
    cat = registry.get(row.discount_category)
    if is_override(row, cat):
        parts.append("Override")
        if not (row.override_reason or "").strip():
            parts.append("Grund fehlt")
    if not row.supplier_article_number.strip():
        parts.append("D fehlt")
    if not row.article_name.strip():
        parts.append("Name fehlt")
    if not row.unit.strip():
        parts.append("Einheit fehlt")
    if not parts:
        parts.append("unverändert")
    return " · ".join(parts)


def _fmt_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _category_cell_value(row: ExportRow) -> str:
    if row.discount_intent == "zero":
        return ZERO_CATEGORY_LABEL
    return row.discount_category


def _cell_value(
    row: ExportRow,
    run: ExportRun,
    registry: dict[str, DiscountCategory],
    field_key: str,
    *,
    after: Decimal | None,
    sale: Decimal | None,
) -> Any:
    spec = BY_KEY.get(field_key)
    if field_key == "discount_category":
        return _category_cell_value(row)
    if field_key == "ek_after":
        return _fmt_cell(after)
    if field_key == "sale_chf":
        return _fmt_cell(sale)
    if field_key == "_status":
        return row_status_label(row, registry)
    if spec is None:
        return ""
    return stored_field_text(row, spec)


def grid_row_values(
    row: ExportRow,
    run: ExportRun,
    registry: dict[str, DiscountCategory],
    fields: list[str] | None = None,
) -> list[Any]:
    after = ek_after_discount(
        row.ek_price_before_discount,
        Decimal(row.base_discount_pct),
        Decimal(row.customer_discount_pct),
    )
    sale = sale_price_chf(after, Decimal(run.markup_pct), Decimal(run.eur_chf_rate))
    order = list(fields or GRID_FIELD_ORDER)
    return [
        _cell_value(row, run, registry, field_key, after=after, sale=sale)
        for field_key in order
    ]


def build_columns(
    registry: dict[str, DiscountCategory],
    *,
    editable: bool,
    article_numbers: list[str] | None = None,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    category_source = [""] + sorted(registry.keys()) + [ZERO_CATEGORY_LABEL]
    ja_nein_required = ["ja", "nein"]
    ja_nein_optional = ["", "ja", "nein"]
    columns: list[dict[str, Any]] = []
    order = list(fields or GRID_FIELD_ORDER)
    for field_name in order:
        spec = BY_KEY.get(field_name)
        read_only = (not editable) or spec is None or spec.edit_policy != "editable"
        width = spec.width if spec else 120
        if field_name == ARTICLE_NUMBER_FIELD:
            width = article_number_column_width(article_numbers or [])
        title = spec.title if spec else field_name
        column: dict[str, Any] = {
            "type": "text",
            "title": title,
            "width": width,
            "readOnly": read_only,
            "name": field_name,
        }
        if spec and spec.note:
            column["tooltip"] = spec.note
        if spec and spec.max_length:
            column["maxLength"] = spec.max_length
        if spec and spec.input_kind == "ja_nein":
            column["type"] = "dropdown"
            column["source"] = (
                ja_nein_required if spec.picker_group == "working" else ja_nein_optional
            )
        elif spec and spec.input_kind == "date":
            column["type"] = "calendar"
            column["options"] = {"format": "DD.MM.YYYY", "time": False}
        elif field_name == "discount_category":
            column["type"] = "dropdown"
            column["source"] = category_source
        columns.append(column)
    return columns


def build_grid_config(
    run: ExportRun,
    rows: list[ExportRow],
    registry: dict[str, DiscountCategory],
    *,
    visible_fields: list[str] | None = None,
) -> dict[str, Any]:
    editable = run.status == "draft"
    fields = list(visible_fields or default_visible_keys())
    return {
        "editsUrl": f"/bezugsquellen/{run.id}/edits",
        "editable": editable,
        "parseFormulas": False,
        "freezeColumns": freeze_column_count(fields),
        "idleMs": FLUSH_IDLE_MS,
        "columns": build_columns(
            registry,
            editable=editable,
            article_numbers=[row.article_number for row in rows],
            fields=fields,
        ),
        "data": [grid_row_values(row, run, registry, fields) for row in rows],
        "rowIds": [str(row.id) for row in rows],
        "rowState": [
            {
                "changed": row_has_changes(row),
                "highlighted": row_is_highlighted(row, registry),
                "unresolved": row.discount_intent == "unresolved",
                "override": is_override(row, registry.get(row.discount_category)),
            }
            for row in rows
        ],
        "fields": fields,
        "editableFields": sorted(EDITABLE_WHITELIST),
    }


def apply_edits(
    db: Session,
    run: ExportRun,
    edits: list[dict[str, Any]],
    registry: dict[str, DiscountCategory],
) -> list[ExportRow]:
    """Apply idle-flushed cell edits; return touched rows for grid refresh."""
    assert_run_editable(run)
    touched: dict[uuid.UUID, ExportRow] = {}
    for edit in edits:
        row_id = uuid.UUID(str(edit["row_id"]))
        field = str(edit.get("field") or "")
        if field not in EDITABLE_WHITELIST:
            raise ValueError(f"Feld nicht bearbeitbar: {field}")
        row = touched.get(row_id) or db.get(ExportRow, row_id)
        if row is None or row.run_id != run.id:
            raise ValueError("Zeile nicht gefunden")
        value = edit.get("value")
        apply_row_patch(db, run, row, {field: value}, registry)
        touched[row_id] = row

    changed = [
        row
        for row in db.scalars(select(ExportRow).where(ExportRow.run_id == run.id))
        if row_has_changes(row)
    ]
    run.included_count = len(changed)
    return list(touched.values())


def bulk_assign_category(
    db: Session,
    run: ExportRun,
    row_ids: list[uuid.UUID],
    category_code: str,
    registry: dict[str, DiscountCategory],
) -> int:
    assert_run_editable(run)
    rows = list(
        db.scalars(
            select(ExportRow).where(
                ExportRow.run_id == run.id,
                ExportRow.id.in_(row_ids),
            )
        )
    )
    for row in rows:
        apply_row_patch(
            db,
            run,
            row,
            {"discount_category": category_code},
            registry,
        )
    run.included_count = sum(
        1
        for r in db.scalars(select(ExportRow).where(ExportRow.run_id == run.id))
        if row_has_changes(r)
    )
    return len(rows)


def _fmt_pct(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal("0.01")))


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal("0.01")))


def validate_and_preview(db: Session, run: ExportRun) -> PreviewReport:
    registry = current_discount_categories(db, run.supplier_id)
    rows = list(
        db.scalars(
            select(ExportRow).where(ExportRow.run_id == run.id).order_by(ExportRow.position)
        )
    )
    included = [r for r in rows if row_has_changes(r)]
    report = PreviewReport(
        included_count=len(included),
        skipped_no_supply_source=list(
            (run.summary_json or {}).get(
                "articles_without_supplier_supply_source_sample", []
            )
        ),
    )
    if included:
        if run.price_entry_date is None:
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="missing_price_entry_date",
                    article_number="",
                    message="Preis-Eintritt ist nicht gesetzt. Bitte im Editor festlegen (Spalte R; Pflicht sobald W geschrieben wird).",
                )
            )
        currency = (run.sales_article_currency or "").strip().upper()
        if currency not in SALES_CURRENCIES:
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="missing_sales_article_currency",
                    article_number="",
                    message="Verkaufsartikel-Währung ist nicht gesetzt. Bitte im Editor EUR oder CHF wählen.",
                )
            )

    from app.supply_export_csv import apply_write_policy, csv_cell_value

    w_spec = BY_KEY["sales_article_number"]
    seen_keys: dict[tuple[str, str], ExportRow] = {}
    for row in rows:
        key = (row.supplier_article_number, row.supplier_number)
        if key in seen_keys:
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="duplicate_match_key",
                    message=(
                        f"Doppelter Match-Schlüssel "
                        f"({row.supplier_article_number}, {row.supplier_number}) "
                        f"— dieselbe Bezugsquelle unter "
                        f"{seen_keys[key].article_number} und {row.article_number}"
                    ),
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        else:
            seen_keys[key] = row

    for row in included:
        if not row.article_name.strip():
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="missing_article_name",
                    message="ARTIKELNAME fehlt",
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        if not row.supplier_article_number.strip():
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="missing_supplier_article_number",
                    message="Lieferantenartikelnummer fehlt",
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        if not row.supplier_number.strip():
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="missing_supplier_number",
                    message="LIEFERANTENNUMMER fehlt",
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        if not row.unit.strip():
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="missing_unit",
                    message="Mengeneinheit fehlt",
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        article_number = (row.article_number or "").strip()
        if not article_number:
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="missing_article_number",
                    message="PROSEMA-Artikelnummer fehlt — Spalte W wäre leer",
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        elif not is_prosema_article_number(article_number):
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="malformed_article_number",
                    message=(
                        f"Artikelnummer {article_number!r} hat nicht die Form "
                        "MMM.SSS.NNNN"
                    ),
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        w_value = apply_write_policy(
            w_spec, csv_cell_value(w_spec, row, registry, run=run)
        )
        if not w_value.strip():
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="empty_sales_article_number",
                    message=(
                        "Verkaufsartikel-Nummer (W) würde leer geschrieben — "
                        "weclapp legt dann einen neuen Artikel aus der "
                        "Lieferantenartikelnummer an"
                    ),
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )

        if row.discount_intent == "unresolved":
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="unresolved_discount",
                    message="Kein auflösbarer Rabatt — Kategorie zuweisen oder «kein Rabatt» wählen",
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )
        elif row.discount_intent == "apply":
            cat = registry.get(row.discount_category)
            if row.discount_category and cat is None:
                report.errors.append(
                    ValidationIssue(
                        level="error",
                        code="unknown_category",
                        message=f"Unbekannte Rabattkategorie {row.discount_category!r}",
                        row_id=row.id,
                        article_number=row.article_number,
                        supplier_article_number=row.supplier_article_number,
                    )
                )
            if is_override(row, cat) and not (row.override_reason or "").strip():
                report.errors.append(
                    ValidationIssue(
                        level="error",
                        code="override_without_reason",
                        message="Abweichung vom Register braucht eine Begründung",
                        row_id=row.id,
                        article_number=row.article_number,
                        supplier_article_number=row.supplier_article_number,
                    )
                )

        locked_keys = locked_extras_keys(row)
        if locked_keys:
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="locked_column_value",
                    message=(
                        "Gesperrte Spalte enthält einen Wert "
                        f"({', '.join(locked_keys)}) — das ist ein Programmfehler, nicht speichern"
                    ),
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )

        if row.ek_price_before_discount is None:
            report.warnings.append(
                ValidationIssue(
                    level="warning",
                    code="missing_ek",
                    message="Kein EK-Preis",
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )

        for spec in FIELDS:
            if spec.max_length is None:
                continue
            text = stored_field_text(row, spec)
            if len(text) > spec.max_length:
                report.warnings.append(
                    ValidationIssue(
                        level="warning",
                        code="char_limit",
                        message=f"{spec.label_internal} länger als {spec.max_length} Zeichen",
                        row_id=row.id,
                        article_number=row.article_number,
                        supplier_article_number=row.supplier_article_number,
                    )
                )

        cat_key = row.discount_category or (
            "kein Rabatt" if row.discount_intent == "zero" else "(ohne)"
        )
        report.by_category[cat_key] = report.by_category.get(cat_key, 0) + 1
        if row.discount_intent == "zero":
            report.explicit_zero_count += 1

        if row.ek_price_before_discount is not None:
            report.ek_before_sum += Decimal(row.ek_price_before_discount)
            after = ek_after_discount(
                Decimal(row.ek_price_before_discount),
                Decimal(row.base_discount_pct),
                Decimal(row.customer_discount_pct),
            )
            if after is not None:
                report.ek_after_sum += after

        # Diff vs weclapp current
        if row.ek_price_before_discount != row.weclapp_current_ek:
            report.weclapp_diff.append(
                DiffEntry(
                    kind="ek_change",
                    supplier_article_number=row.supplier_article_number,
                    article_number=row.article_number,
                    field="ek",
                    old_value=_fmt_money(row.weclapp_current_ek),
                    new_value=_fmt_money(row.ek_price_before_discount),
                )
            )
        if row.discount_intent != "unresolved":
            new_d1 = (
                Decimal("0")
                if row.discount_intent == "zero"
                else Decimal(row.base_discount_pct)
            )
            new_d2 = (
                Decimal("0")
                if row.discount_intent == "zero"
                else Decimal(row.customer_discount_pct)
            )
            if row.weclapp_current_base_discount_pct is not None and new_d1 != Decimal(
                row.weclapp_current_base_discount_pct
            ):
                report.weclapp_diff.append(
                    DiffEntry(
                        kind="discount_change",
                        supplier_article_number=row.supplier_article_number,
                        article_number=row.article_number,
                        field="d1",
                        old_value=_fmt_pct(row.weclapp_current_base_discount_pct),
                        new_value=_fmt_pct(new_d1),
                    )
                )
            if (
                row.weclapp_current_customer_discount_pct is not None
                and new_d2 != Decimal(row.weclapp_current_customer_discount_pct)
            ):
                report.weclapp_diff.append(
                    DiffEntry(
                        kind="discount_change",
                        supplier_article_number=row.supplier_article_number,
                        article_number=row.article_number,
                        field="d2",
                        old_value=_fmt_pct(row.weclapp_current_customer_discount_pct),
                        new_value=_fmt_pct(new_d2),
                    )
                )

    # Prior-run diff (all rows in this pull vs previous export's included set)
    prior = previous_exported_run(db, supplier_id=run.supplier_id, before=run)
    if prior is not None:
        prior_rows = {
            r.supplier_article_number: r
            for r in db.scalars(
                select(ExportRow).where(
                    ExportRow.run_id == prior.id,
                    ExportRow.included.is_(True),
                )
            )
        }
        current_by_d = {r.supplier_article_number: r for r in rows}
        for d_num, crow in current_by_d.items():
            prow = prior_rows.get(d_num)
            if prow is None:
                if crow.included or row_has_changes(crow):
                    report.prior_run_diff.append(
                        DiffEntry(
                            kind="new",
                            supplier_article_number=d_num,
                            article_number=crow.article_number,
                        )
                    )
                continue
            if row_has_changes(crow) and crow.ek_price_before_discount != prow.ek_price_before_discount:
                report.prior_run_diff.append(
                    DiffEntry(
                        kind="ek_change",
                        supplier_article_number=d_num,
                        article_number=crow.article_number,
                        field="ek",
                        old_value=_fmt_money(prow.ek_price_before_discount),
                        new_value=_fmt_money(crow.ek_price_before_discount),
                    )
                )
            if row_has_changes(crow) and (
                crow.base_discount_pct != prow.base_discount_pct
                or crow.customer_discount_pct != prow.customer_discount_pct
                or crow.discount_intent != prow.discount_intent
            ):
                report.prior_run_diff.append(
                    DiffEntry(
                        kind="discount_change",
                        supplier_article_number=d_num,
                        article_number=crow.article_number,
                        field="discount",
                        old_value=f"{prow.discount_intent}:{_fmt_pct(prow.base_discount_pct)}/{_fmt_pct(prow.customer_discount_pct)}",
                        new_value=f"{crow.discount_intent}:{_fmt_pct(crow.base_discount_pct)}/{_fmt_pct(crow.customer_discount_pct)}",
                    )
                )
        for d_num, prow in prior_rows.items():
            if d_num not in current_by_d:
                report.prior_run_diff.append(
                    DiffEntry(
                        kind="dropped",
                        supplier_article_number=d_num,
                        article_number=prow.article_number,
                    )
                )

    from app.supply_export_csv import locked_write_violations, written_column_counts

    report.written_columns = written_column_counts(included, registry, run=run)
    for row in included:
        locked_headers = locked_write_violations(row, registry, run=run)
        if locked_headers:
            report.errors.append(
                ValidationIssue(
                    level="error",
                    code="locked_column_value",
                    message=(
                        "Gesperrte Exportspalte würde geschrieben: "
                        + ", ".join(locked_headers)
                    ),
                    row_id=row.id,
                    article_number=row.article_number,
                    supplier_article_number=row.supplier_article_number,
                )
            )

    return report


def blocking_counts(db: Session, run: ExportRun) -> dict[str, int]:
    rows = list(db.scalars(select(ExportRow).where(ExportRow.run_id == run.id)))
    changed = [r for r in rows if row_has_changes(r)]
    unresolved = sum(1 for r in changed if r.discount_intent == "unresolved")
    missing_mandatory = sum(
        1
        for r in changed
        if not r.article_name.strip()
        or not r.supplier_article_number.strip()
        or not r.supplier_number.strip()
        or not r.unit.strip()
        or not (r.article_number or "").strip()
        or not is_prosema_article_number(r.article_number)
    )
    seen: set[tuple[str, str]] = set()
    duplicate_match_key = 0
    for row in rows:
        key = (row.supplier_article_number, row.supplier_number)
        if key in seen:
            duplicate_match_key += 1
        else:
            seen.add(key)
    return {
        "unresolved_included": unresolved,
        "missing_mandatory_included": missing_mandatory,
        "missing_price_entry": bool(changed) and run.price_entry_date is None,
        "missing_sales_currency": bool(changed)
        and (run.sales_article_currency or "").strip().upper() not in SALES_CURRENCIES,
        "duplicate_match_key": duplicate_match_key,
        "included": len(changed),
        "total": int(run.row_count or 0),
    }
