"""Assign already-uploaded Shopify files to products by article number (SKU).

Dennis has uploaded images directly to Shopify's Files section.  This script
matches those files to products using the article-number pattern in the
filename, then attaches them via productCreateMedia.

Usage:
    python -m scripts.shopify.assign_images                  # dry-run report
    python -m scripts.shopify.assign_images --assign         # actually assign
    python -m scripts.shopify.assign_images --article 010.010.0010 --assign
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ARTICLE_RE = re.compile(r"(\d{3}\.\d{3}\.\d{4})")
SHOPIFY_DUPLICATE_SUFFIX_RE = re.compile(
    r"^(?P<base>.+)_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass
class ShopifyFile:
    file_id: str
    article_number: str
    url: str
    alt: str
    is_color: bool


@dataclass
class AssignCandidate:
    article_number: str
    product_id: str
    product_title: str
    files: list[ShopifyFile]
    media_count: int


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _classify_color(url: str, alt: str) -> bool:
    """Heuristic: color photos vs line drawings based on path/alt text."""
    combined = (url + " " + alt).lower()
    if "strichzeichnung" in combined or "drawing" in combined:
        return False
    if "farblich" in combined or "farbig" in combined or "color" in combined:
        return True
    # Default to color if we can't tell
    return True


def _extract_article(url: str, alt: str) -> str | None:
    for source in (alt, url.split("/")[-1] if "/" in url else url):
        m = ARTICLE_RE.search(source)
        if m:
            return m.group(1)
    return None


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    return Path(path).name


def _normalized_file_key(url: str) -> str:
    filename = _filename_from_url(url)
    path = Path(filename)
    match = SHOPIFY_DUPLICATE_SUFFIX_RE.match(path.stem)
    stem = match.group("base") if match else path.stem
    return f"{stem.lower()}{path.suffix.lower()}"


def _dedupe_files(files: list[ShopifyFile]) -> list[ShopifyFile]:
    deduped: dict[str, ShopifyFile] = {}
    for file in sorted(files, key=lambda item: (_normalized_file_key(item.url), item.url)):
        key = _normalized_file_key(file.url)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = file
            continue
        existing_name = _filename_from_url(existing.url)
        current_name = _filename_from_url(file.url)
        # Prefer the original Shopify filename over duplicate collision variants.
        if "_" in Path(existing_name).stem and "_" not in Path(current_name).stem:
            deduped[key] = file
    return list(deduped.values())


def run_assign(
    *,
    output_path: Path,
    assign: bool = False,
    skip_with_media: bool = True,
    limit: int | None = None,
    article_numbers: set[str] | None = None,
) -> dict[str, int]:
    from scripts.shopify.client import ShopifyClient, ShopifyError
    from scripts.shopify.config import load_config
    from scripts.shopify.images import product_from_shopify_node

    config = load_config()
    client = ShopifyClient(config)

    # 1. Collect all files from Shopify's Files section
    print("Lade Dateien aus Shopify …", file=sys.stderr)
    files_by_article: dict[str, list[ShopifyFile]] = {}
    file_count = 0
    for node in client.iter_files():
        file_id = node.get("id", "")
        image_data = node.get("image") or {}
        url = image_data.get("url") or image_data.get("originalSrc") or node.get("url") or ""
        alt = node.get("alt") or ""

        if not url:
            continue

        article = _extract_article(url, alt)
        if article is None:
            continue
        if article_numbers is not None and article not in article_numbers:
            continue

        sf = ShopifyFile(
            file_id=file_id,
            article_number=article,
            url=url,
            alt=alt,
            is_color=_classify_color(url, alt),
        )
        files_by_article.setdefault(article, []).append(sf)
        file_count += 1

    print(f"  {file_count} Dateien für {len(files_by_article)} Artikel gefunden", file=sys.stderr)

    # 2. Collect products
    print("Lade Produkte aus Shopify …", file=sys.stderr)
    products_by_sku: dict[str, tuple[str, str, int]] = {}
    for node in client.iter_products():
        ref = product_from_shopify_node(node)
        if ref is None:
            continue
        products_by_sku[ref.sku] = (ref.product_id, ref.title, ref.media_count)

    print(f"  {len(products_by_sku)} Produkte mit SKU", file=sys.stderr)

    # 3. Build candidates
    candidates: list[AssignCandidate] = []
    no_product = 0
    already_has = 0
    for article, files in sorted(files_by_article.items()):
        if article not in products_by_sku:
            no_product += 1
            continue
        product_id, title, media_count = products_by_sku[article]
        if skip_with_media and media_count > 0:
            already_has += 1
            continue
        files = _dedupe_files(files)
        # Sort: color first, then drawings
        files.sort(key=lambda f: (not f.is_color, f.url))
        candidates.append(AssignCandidate(
            article_number=article,
            product_id=product_id,
            product_title=title,
            files=files,
            media_count=media_count,
        ))

    if limit is not None:
        candidates = candidates[:limit]

    # 4. Write report CSV
    _write_report(output_path, candidates)

    stats = {
        "files_matched": file_count,
        "articles_with_files": len(files_by_article),
        "products_with_sku": len(products_by_sku),
        "no_product_found": no_product,
        "already_has_media": already_has,
        "assign_candidates": len(candidates),
        "assigned": 0,
        "errors": 0,
    }

    if not assign:
        return stats

    # 5. Assign files to products
    print(f"\nZuordnung für {len(candidates)} Produkte …", file=sys.stderr)
    for i, cand in enumerate(candidates, 1):
        media_input = []
        for sf in cand.files:
            kind = "Farbfoto" if sf.is_color else "Strichzeichnung"
            media_input.append({
                "originalSource": sf.url,
                "mediaContentType": "IMAGE",
                "alt": sf.alt or f"{cand.article_number} – {kind}",
            })
        try:
            client.product_create_media(cand.product_id, media_input)
            stats["assigned"] += 1
            print(
                f"  [{i}/{len(candidates)}] OK {cand.article_number} "
                f"({len(cand.files)} Bild(er))",
                file=sys.stderr,
            )
        except ShopifyError as exc:
            stats["errors"] += 1
            print(
                f"  [{i}/{len(candidates)}] FEHLER {cand.article_number}: {exc}",
                file=sys.stderr,
            )

    return stats


def _format_shopify_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, list) and detail:
        parts: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                message = str(item.get("message") or "").strip()
                required = (
                    ((item.get("extensions") or {}).get("requiredAccess"))
                    if isinstance(item.get("extensions"), dict)
                    else None
                )
                if message and required:
                    parts.append(f"{message} Benoetigt: {required}")
                elif message:
                    parts.append(message)
        if parts:
            return " | ".join(parts)
    return str(exc)


def _write_report(path: Path, candidates: list[AssignCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["article_number", "product_id", "product_title", "media_count", "files_to_assign", "file_urls"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter=";")
        writer.writeheader()
        for cand in candidates:
            writer.writerow({
                "article_number": cand.article_number,
                "product_id": cand.product_id,
                "product_title": cand.product_title,
                "media_count": cand.media_count,
                "files_to_assign": len(cand.files),
                "file_urls": " | ".join(f.url for f in cand.files),
            })


def main(argv: list[str] | None = None) -> int:
    _ensure_project_root()
    from scripts.paths import OUTPUT_SHOPIFY, resolve_path

    parser = argparse.ArgumentParser(
        description=(
            "Bereits in Shopify hochgeladene Bilder anhand der Artikelnummer "
            "den Produkten zuordnen."
        )
    )
    parser.add_argument(
        "--assign",
        action="store_true",
        help="Bilder tatsächlich den Produkten zuordnen (sonst nur Report)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV-Ausgabe (Standard: output/shopify/assign_images_TIMESTAMP.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximale Anzahl Produkte",
    )
    parser.add_argument(
        "--article",
        action="append",
        default=[],
        help="Nur diese Artikelnummer(n), mehrfach möglich",
    )
    parser.add_argument(
        "--include-with-media",
        action="store_true",
        help="Auch Produkte zuordnen, die bereits Bilder haben",
    )
    args = parser.parse_args(argv)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = resolve_path(
        args.output or (OUTPUT_SHOPIFY / f"assign_images_{timestamp}.csv")
    )
    article_numbers = set(args.article) if args.article else None

    print(f"Report: {output}", file=sys.stderr)
    if args.assign:
        print("Modus: ZUORDNUNG", file=sys.stderr)
    else:
        print("Modus: nur Report (--assign zum Zuordnen)", file=sys.stderr)

    try:
        stats = run_assign(
            output_path=output,
            assign=args.assign,
            skip_with_media=not args.include_with_media,
            limit=args.limit,
            article_numbers=article_numbers,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Fehler: {_format_shopify_error(exc)}", file=sys.stderr)
        return 1

    print("\nZusammenfassung", file=sys.stderr)
    for key, value in stats.items():
        print(f"  {key}: {value}", file=sys.stderr)
    print(f"CSV geschrieben: {output}", file=sys.stderr)

    return 0 if stats.get("errors", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
