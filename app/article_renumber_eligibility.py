"""Eligibility checks for admin article renumbering after subgroup reassignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Hauptgruppe, SupplierArticleAlias, Untergruppe
from app.weclapp_categories import GroupSyncIssue, compare_group_registry, list_article_categories
from core.numbering import parse_group_codes
from scripts.weclapp.client import WeclappClient

DOCUMENT_ITEM_ENTITIES = (
    "purchaseOrderItem",
    "salesOrderItem",
    "shipmentItem",
    "incomingGoodsItem",
    "salesInvoiceItem",
    "purchaseInvoiceItem",
    "quotationItem",
)

REASON_SUPPLY_SOURCE = "warning_supply_source"
REASON_STOCK = "ineligible_stock"
REASON_MOVEMENT = "ineligible_movement"
REASON_DOCUMENT = "ineligible_document"
REASON_REGISTRY = "ineligible_registry_mismatch"
REASON_NO_CHANGE = "ineligible_no_change"
REASON_ALIAS = "ineligible_alias_row"

REASON_LABELS_DE: dict[str, str] = {
    REASON_SUPPLY_SOURCE: "Bezugsquelle vorhanden (Warnung)",
    REASON_STOCK: "Lagerbestand vorhanden",
    REASON_MOVEMENT: "Lagerbewegung vorhanden",
    REASON_DOCUMENT: "In Belegpositionen referenziert",
    REASON_REGISTRY: "Gruppenregister nicht abgestimmt",
    REASON_NO_CHANGE: "Nummer passt bereits zur Kategorie",
    REASON_ALIAS: "Lieferanten-Alias vorhanden",
}


@dataclass(frozen=True)
class SupplySourceWarningLine:
    supplier_name: str
    supplier_number: str
    supplier_article_number: str


@dataclass(frozen=True)
class EligibilityResult:
    ok: bool
    reason_code: str | None
    checks: dict[str, bool]
    supply_source_warning: tuple[SupplySourceWarningLine, ...] = ()

    @staticmethod
    def from_checks(
        checks: dict[str, bool],
        *,
        supply_source_warning: tuple[SupplySourceWarningLine, ...] = (),
    ) -> EligibilityResult:
        order = (
            ("no_mismatch", REASON_NO_CHANGE),
            ("no_alias_row", REASON_ALIAS),
            ("no_stock", REASON_STOCK),
            ("no_movement", REASON_MOVEMENT),
            ("no_document", REASON_DOCUMENT),
            ("registry_ok", REASON_REGISTRY),
        )
        for key, code in order:
            if not checks.get(key, False):
                return EligibilityResult(
                    ok=False,
                    reason_code=code,
                    checks=checks,
                    supply_source_warning=supply_source_warning,
                )
        return EligibilityResult(
            ok=True,
            reason_code=None,
            checks=checks,
            supply_source_warning=supply_source_warning,
        )


@dataclass
class RenumberPrefetch:
    stock_article_ids: set[str] = field(default_factory=set)
    movement_article_ids: set[str] = field(default_factory=set)
    document_article_ids: set[str] = field(default_factory=set)
    category_id_to_pair: dict[str, tuple[str, str]] = field(default_factory=dict)
    registry_issues: list[GroupSyncIssue] = field(default_factory=list)
    tools_haupt: dict[str, str] = field(default_factory=dict)
    tools_unter: dict[tuple[str, str], str] = field(default_factory=dict)
    manual_alias_weclapp_ids: set[str] = field(default_factory=set)
    manual_alias_article_numbers: set[str] = field(default_factory=set)
    live_supply_source_alias_weclapp_ids: set[str] = field(default_factory=set)
    live_supply_source_alias_article_numbers: set[str] = field(default_factory=set)


def tools_group_maps(db: Session) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    haupt = {
        row.code: row.name
        for row in db.scalars(select(Hauptgruppe))
    }
    unter: dict[tuple[str, str], str] = {}
    for row in db.scalars(select(Untergruppe)):
        parent = row.hauptgruppe
        unter[(parent.code, row.code)] = row.name
    return haupt, unter


def _article_id_from_row(row: dict[str, Any]) -> str:
    for key in ("articleId", "article_id"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def prefetch_renumber_context(db: Session, client: WeclappClient) -> RenumberPrefetch:
    ctx = RenumberPrefetch()
    ctx.tools_haupt, ctx.tools_unter = tools_group_maps(db)
    categories = list_article_categories(client)
    from app.weclapp_categories import _weclapp_coded_tree

    _haupt, unter, _uncoded = _weclapp_coded_tree(categories)
    by_id = {str(row.get("id") or ""): row for row in categories if isinstance(row, dict)}
    for cat_id, row in by_id.items():
        if not cat_id:
            continue
        parent_id = str(row.get("parentCategoryId") or "")
        if not parent_id:
            continue
        parent = by_id.get(parent_id) or {}
        parent_code = str(parent.get("description") or "").strip()
        child_code = str(row.get("description") or "").strip()
        if len(parent_code) == 3 and parent_code.isdigit() and len(child_code) == 3 and child_code.isdigit():
            ctx.category_id_to_pair[cat_id] = (parent_code, child_code)
    ctx.registry_issues = compare_group_registry(
        ctx.tools_haupt, ctx.tools_unter, categories
    )
    for wc_id, number in db.execute(
        select(SupplierArticleAlias.weclapp_article_id, SupplierArticleAlias.article_number).where(
            SupplierArticleAlias.source == "manual"
        )
    ):
        if wc_id:
            ctx.manual_alias_weclapp_ids.add(str(wc_id).strip())
        if number:
            ctx.manual_alias_article_numbers.add(str(number).strip())
    live_supply_source_aliases = text(
        """
        SELECT DISTINCT a.weclapp_article_id, a.article_number
        FROM supplier_article_aliases a
        INNER JOIN weclapp_supply_source_links l
          ON l.weclapp_article_id = a.weclapp_article_id
         AND l.article_number = a.article_number
        INNER JOIN weclapp_supply_sources ss
          ON ss.weclapp_id = l.supply_source_weclapp_id
         AND ss.supplier_article_number = a.supplier_article_number
        INNER JOIN suppliers s
          ON s.weclapp_party_id = l.supplier_party_id
         AND s.id = a.supplier_id
        WHERE a.source = 'supply_source'
        """
    )
    for wc_id, number in db.execute(live_supply_source_aliases):
        if wc_id:
            ctx.live_supply_source_alias_weclapp_ids.add(str(wc_id).strip())
        if number:
            ctx.live_supply_source_alias_article_numbers.add(str(number).strip())
    for row in client.iter_pages("warehouseStock"):
        if not isinstance(row, dict):
            continue
        aid = _article_id_from_row(row)
        if aid:
            ctx.stock_article_ids.add(aid)
    for row in client.iter_pages("warehouseStockMovement"):
        if not isinstance(row, dict):
            continue
        aid = _article_id_from_row(row)
        if aid:
            ctx.movement_article_ids.add(aid)
    for entity in DOCUMENT_ITEM_ENTITIES:
        for row in client.iter_pages(entity):
            if not isinstance(row, dict):
                continue
            aid = _article_id_from_row(row)
            if aid:
                ctx.document_article_ids.add(aid)
    return ctx


def category_pair_from_article(
    article: dict[str, Any],
    ctx: RenumberPrefetch,
) -> tuple[str, str] | None:
    cat_id = str(article.get("articleCategoryId") or "").strip()
    if not cat_id:
        return None
    return ctx.category_id_to_pair.get(cat_id)


def registry_blocks_destination(
    ctx: RenumberPrefetch,
    destination: tuple[str, str],
) -> bool:
    haupt, unter = destination
    if haupt not in ctx.tools_haupt or (haupt, unter) not in ctx.tools_unter:
        return True
    label = f"{haupt}.{unter}"
    for issue in ctx.registry_issues:
        if issue.kind != "name_mismatch":
            continue
        if issue.code == label or issue.code == haupt:
            return True
    return False


def has_manual_alias(
    *,
    weclapp_id: str,
    article_number: str,
    ctx: RenumberPrefetch,
) -> bool:
    return (
        weclapp_id in ctx.manual_alias_weclapp_ids
        or article_number in ctx.manual_alias_article_numbers
    )


def has_live_supply_source_alias(
    *,
    weclapp_id: str,
    article_number: str,
    ctx: RenumberPrefetch,
) -> bool:
    return (
        weclapp_id in ctx.live_supply_source_alias_weclapp_ids
        or article_number in ctx.live_supply_source_alias_article_numbers
    )


def collect_supply_source_warning_lines(
    db: Session,
    *,
    weclapp_id: str,
    article_number: str,
    article: dict[str, Any],
    ctx: RenumberPrefetch,
) -> tuple[SupplySourceWarningLine, ...]:
    """Supplier + SAN lines for preview warning (live SS and/or supply_source aliases)."""
    from app.models import Supplier, SupplierArticleAlias, WeclappSupplySource

    if not live_has_supply_source(article) and not has_live_supply_source_alias(
        weclapp_id=weclapp_id,
        article_number=article_number,
        ctx=ctx,
    ):
        return ()

    seen: set[tuple[str, str]] = set()
    lines: list[SupplySourceWarningLine] = []

    def add_line(name: str, number: str, san: str) -> None:
        key = (number.strip(), san.strip())
        if not san.strip() or key in seen:
            return
        seen.add(key)
        lines.append(
            SupplySourceWarningLine(
                supplier_name=(name or number).strip(),
                supplier_number=number.strip(),
                supplier_article_number=san.strip(),
            )
        )

    ss_ids: list[str] = []
    for item in article.get("supplySources") or []:
        if isinstance(item, dict):
            sid = str(item.get("articleSupplySourceId") or "").strip()
            if sid:
                ss_ids.append(sid)
    primary = str(article.get("primarySupplySourceId") or "").strip()
    if primary:
        ss_ids.append(primary)
    for ss_id in dict.fromkeys(ss_ids):
        ss = db.get(WeclappSupplySource, ss_id)
        if ss is None:
            continue
        supplier = db.scalars(
            select(Supplier).where(Supplier.weclapp_party_id == ss.supplier_party_id)
        ).first()
        name = supplier.name if supplier is not None else ss.supplier_number
        add_line(name, ss.supplier_number, ss.supplier_article_number)

    for alias in db.scalars(
        select(SupplierArticleAlias).where(
            SupplierArticleAlias.source == "supply_source",
            SupplierArticleAlias.weclapp_article_id == weclapp_id,
            SupplierArticleAlias.article_number == article_number,
        )
    ):
        supplier = db.get(Supplier, alias.supplier_id)
        if supplier is None:
            continue
        add_line(supplier.name, supplier.supplier_number, alias.supplier_article_number)

    if not lines and live_has_supply_source(article):
        add_line("—", "—", "—")
    return tuple(lines)


def live_has_supply_source(article: dict[str, Any]) -> bool:
    sources = article.get("supplySources")
    if isinstance(sources, list) and len(sources) > 0:
        return True
    primary = article.get("primarySupplySourceId")
    return primary is not None and str(primary).strip() != ""


def evaluate_eligibility(
    *,
    article: dict[str, Any],
    weclapp_id: str,
    ctx: RenumberPrefetch,
    db: Session | None = None,
) -> EligibilityResult:
    number = str(article.get("articleNumber") or "").strip()
    number_pair = parse_group_codes(number)
    category_pair = category_pair_from_article(article, ctx)
    mismatch = (
        number_pair is not None
        and category_pair is not None
        and number_pair != category_pair
    )
    registry_ok = (
        category_pair is not None
        and not registry_blocks_destination(ctx, category_pair)
    )
    has_manual = has_manual_alias(
        weclapp_id=weclapp_id, article_number=number, ctx=ctx
    )
    checks = {
        "no_mismatch": mismatch,
        "no_alias_row": not has_manual,
        "no_stock": weclapp_id not in ctx.stock_article_ids,
        "no_movement": weclapp_id not in ctx.movement_article_ids,
        "no_document": weclapp_id not in ctx.document_article_ids,
        "registry_ok": registry_ok,
    }
    warning_lines: tuple[SupplySourceWarningLine, ...] = ()
    if db is not None:
        warning_lines = collect_supply_source_warning_lines(
            db,
            weclapp_id=weclapp_id,
            article_number=number,
            article=article,
            ctx=ctx,
        )
    return EligibilityResult.from_checks(checks, supply_source_warning=warning_lines)


def destination_pair_for_article(
    article: dict[str, Any],
    ctx: RenumberPrefetch,
) -> tuple[str, str] | None:
    return category_pair_from_article(article, ctx)
