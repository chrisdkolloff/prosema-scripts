"""Match Shopify products (by SKU/article number) to local Dural image folders."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE = Path(
    "/Users/chris-mbp/Library/CloudStorage/Dropbox/PPROSEMA/Dural/Bilder Preisliste"
)
COLOR_DIR_NAME = "Bilder PL farblich umbenannt"
DRAWING_DIR_NAME = "Bilder PL Strichzeichnung umbenannt"

# e.g. 010.010.0010-1.JPG  or  010.010.0010.JPG
FILENAME_RE = re.compile(
    r"^(?P<article>\d{3}\.\d{3}\.\d{4})(?:-(?P<index>\d+))?(?P<ext>\.[A-Za-z0-9]+)$"
)


@dataclass
class LocalImages:
    article_number: str
    color: list[Path] = field(default_factory=list)
    drawing: list[Path] = field(default_factory=list)

    @property
    def ordered_paths(self) -> list[Path]:
        """Hero = color photos first, then line drawings."""
        return list(self.color) + list(self.drawing)

    @property
    def has_any(self) -> bool:
        return bool(self.color or self.drawing)


@dataclass
class ShopifyProductRef:
    product_id: str
    title: str
    handle: str
    status: str
    sku: str
    media_count: int


@dataclass
class MatchRow:
    article_number: str
    product_id: str
    title: str
    handle: str
    status: str
    media_count: int
    color_count: int
    drawing_count: int
    color_files: str
    drawing_files: str
    match_status: str
    upload_plan: str


def parse_image_filename(filename: str) -> tuple[str, int] | None:
    match = FILENAME_RE.match(filename)
    if not match:
        return None
    article = match.group("article")
    index = int(match.group("index") or "1")
    return article, index


def _scan_folder(folder: Path) -> dict[str, list[Path]]:
    by_article: dict[str, list[tuple[int, Path]]] = {}
    if not folder.is_dir():
        return {}
    for path in folder.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        parsed = parse_image_filename(path.name)
        if parsed is None:
            continue
        article, index = parsed
        by_article.setdefault(article, []).append((index, path))

    result: dict[str, list[Path]] = {}
    for article, entries in by_article.items():
        entries.sort(key=lambda item: (item[0], item[1].name.lower()))
        result[article] = [path for _, path in entries]
    return result


def load_local_images(
    *,
    base_dir: Path = DEFAULT_BASE,
    color_dir_name: str = COLOR_DIR_NAME,
    drawing_dir_name: str = DRAWING_DIR_NAME,
) -> dict[str, LocalImages]:
    color_map = _scan_folder(base_dir / color_dir_name)
    drawing_map = _scan_folder(base_dir / drawing_dir_name)
    articles = sorted(set(color_map) | set(drawing_map))
    return {
        article: LocalImages(
            article_number=article,
            color=color_map.get(article, []),
            drawing=drawing_map.get(article, []),
        )
        for article in articles
    }


def product_from_shopify_node(node: dict) -> ShopifyProductRef | None:
    variants = ((node.get("variants") or {}).get("nodes")) or []
    sku = ""
    for variant in variants:
        candidate = (variant.get("sku") or "").strip()
        if candidate:
            sku = candidate
            break
    if not sku:
        return None
    media_nodes = ((node.get("media") or {}).get("nodes")) or []
    return ShopifyProductRef(
        product_id=node["id"],
        title=node.get("title") or "",
        handle=node.get("handle") or "",
        status=node.get("status") or "",
        sku=sku,
        media_count=len(media_nodes),
    )


def classify_match(
    product: ShopifyProductRef,
    local: LocalImages | None,
) -> MatchRow:
    if local is None or not local.has_any:
        status = "no_local_images"
        plan = ""
    elif product.media_count > 0:
        status = "already_has_media"
        plan = _plan_text(local)
    elif local.color and local.drawing:
        status = "ready"
        plan = _plan_text(local)
    elif local.color:
        status = "color_only"
        plan = _plan_text(local)
    else:
        status = "drawing_only"
        plan = _plan_text(local)

    return MatchRow(
        article_number=product.sku,
        product_id=product.product_id,
        title=product.title,
        handle=product.handle,
        status=product.status,
        media_count=product.media_count,
        color_count=len(local.color) if local else 0,
        drawing_count=len(local.drawing) if local else 0,
        color_files=";".join(p.name for p in local.color) if local else "",
        drawing_files=";".join(p.name for p in local.drawing) if local else "",
        match_status=status,
        upload_plan=plan,
    )


def _plan_text(local: LocalImages) -> str:
    parts: list[str] = []
    for index, path in enumerate(local.ordered_paths, start=1):
        role = "hero" if index == 1 else f"image_{index}"
        kind = "color" if path in local.color else "drawing"
        parts.append(f"{role}={kind}:{path.name}")
    return " | ".join(parts)


def build_match_rows(
    products: list[ShopifyProductRef],
    local_images: dict[str, LocalImages],
) -> list[MatchRow]:
    rows = [
        classify_match(product, local_images.get(product.sku))
        for product in products
    ]
    rows.sort(key=lambda row: (row.match_status, row.article_number))
    return rows


MATCH_CSV_FIELDS = [
    "article_number",
    "match_status",
    "product_id",
    "title",
    "handle",
    "status",
    "media_count",
    "color_count",
    "drawing_count",
    "color_files",
    "drawing_files",
    "upload_plan",
]


def write_match_csv(path: Path, rows: list[MatchRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=MATCH_CSV_FIELDS,
            delimiter=";",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: getattr(row, field) for field in MATCH_CSV_FIELDS})


def summarize_rows(rows: list[MatchRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.match_status] = counts.get(row.match_status, 0) + 1
    counts["total_products_with_sku"] = len(rows)
    return counts
