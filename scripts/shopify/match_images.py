"""Match Shopify products to local Dural images; optionally upload them."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


@dataclass
class UploadStats:
    uploaded: int = 0
    skipped: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)


def run_match(
    *,
    base_dir: Path,
    output_path: Path,
    upload: bool = False,
    skip_with_media: bool = True,
    limit: int | None = None,
    article_numbers: set[str] | None = None,
) -> tuple[dict[str, int], UploadStats]:
    from scripts.shopify.client import ShopifyClient, ShopifyError
    from scripts.shopify.config import load_config
    from scripts.shopify.images import (
        LocalImages,
        MatchRow,
        ShopifyProductRef,
        build_match_rows,
        load_local_images,
        product_from_shopify_node,
        summarize_rows,
        write_match_csv,
    )

    config = load_config()
    client = ShopifyClient(config)
    local_images = load_local_images(base_dir=base_dir)

    products: list[ShopifyProductRef] = []
    products_without_sku = 0
    for node in client.iter_products():
        ref = product_from_shopify_node(node)
        if ref is None:
            products_without_sku += 1
            continue
        if article_numbers is not None and ref.sku not in article_numbers:
            continue
        products.append(ref)

    rows = build_match_rows(products, local_images)
    write_match_csv(output_path, rows)
    summary = summarize_rows(rows)
    summary["products_without_sku"] = products_without_sku
    summary["local_articles_with_images"] = len(local_images)

    upload_stats = UploadStats()
    if not upload:
        return summary, upload_stats

    candidates = [
        row
        for row in rows
        if row.match_status in {"ready", "color_only", "drawing_only"}
        or (not skip_with_media and row.match_status == "already_has_media")
    ]
    if skip_with_media:
        candidates = [row for row in candidates if row.media_count == 0]

    if limit is not None:
        candidates = candidates[:limit]

    total = len(candidates)
    print(f"Upload-Kandidaten: {total}", file=sys.stderr)

    for index, row in enumerate(candidates, start=1):
        local = local_images.get(row.article_number)
        if local is None or not local.has_any:
            upload_stats.skipped += 1
            continue
        try:
            _upload_product_images(client, row, local)
            upload_stats.uploaded += 1
            upload_stats.messages.append(
                f"OK {row.article_number}: {len(local.ordered_paths)} Bild(er)"
            )
            print(
                f"  [{index}/{total}] OK {row.article_number} "
                f"({len(local.ordered_paths)} Bild(er))",
                file=sys.stderr,
            )
        except ShopifyError as exc:
            upload_stats.errors += 1
            upload_stats.messages.append(
                f"FEHLER {row.article_number}: {exc} {exc.detail or ''}"
            )
            print(
                f"  [{index}/{total}] FEHLER {row.article_number}: {exc}",
                file=sys.stderr,
            )

    return summary, upload_stats


def _upload_product_images(client, row: MatchRow, local: LocalImages) -> None:
    paths = local.ordered_paths
    targets = client.staged_upload_targets(paths)
    resource_urls: list[str] = []
    for path, target in zip(paths, targets, strict=True):
        resource_urls.append(client.upload_file_to_staged_target(path, target))

    media = []
    for path, resource_url in zip(paths, resource_urls, strict=True):
        kind = "Farbfoto" if path in local.color else "Strichzeichnung"
        media.append(
            {
                "originalSource": resource_url,
                "mediaContentType": "IMAGE",
                "alt": f"{row.article_number} – {kind}",
            }
        )
    client.product_create_media(row.product_id, media)


def main(argv: list[str] | None = None) -> int:
    _ensure_project_root()
    from scripts.paths import OUTPUT_SHOPIFY, resolve_path
    from scripts.shopify.images import DEFAULT_BASE

    parser = argparse.ArgumentParser(
        description=(
            "Shopify-Produkte anhand der Artikelnummer (SKU) mit lokalen "
            "Dural-Bildern abgleichen; optional Bilder hochladen "
            "(Hero = Farbfoto, danach Strichzeichnung)."
        )
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_BASE,
        help="Ordner 'Bilder Preisliste' mit den umbenannten Unterordnern",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV-Ausgabe (Standard: output/shopify/image_match_TIMESTAMP.csv)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Bilder tatsächlich nach Shopify hochladen (sonst nur Matching-Report)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximale Anzahl Produkte beim Upload (Pilot)",
    )
    parser.add_argument(
        "--article",
        action="append",
        default=[],
        help="Nur diese Artikelnummer(n) (SKU), mehrfach möglich",
    )
    parser.add_argument(
        "--include-with-media",
        action="store_true",
        help="Auch Produkte hochladen, die bereits Bilder haben",
    )
    args = parser.parse_args(argv)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = resolve_path(
        args.output
        or (OUTPUT_SHOPIFY / f"image_match_{timestamp}.csv")
    )
    article_numbers = set(args.article) if args.article else None

    print(f"Bildordner: {args.base_dir}", file=sys.stderr)
    print(f"Report:     {output}", file=sys.stderr)
    if args.upload:
        print(
            "Upload:     AN"
            + (f" (limit={args.limit})" if args.limit is not None else ""),
            file=sys.stderr,
        )
    else:
        print("Upload:     aus (nur Matching)", file=sys.stderr)

    try:
        summary, upload_stats = run_match(
            base_dir=resolve_path(args.base_dir)
            if not args.base_dir.is_absolute()
            else args.base_dir,
            output_path=output,
            upload=args.upload,
            skip_with_media=not args.include_with_media,
            limit=args.limit,
            article_numbers=article_numbers,
        )
    except Exception as exc:  # noqa: BLE001 — CLI top-level
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    print("", file=sys.stderr)
    print("Matching-Zusammenfassung", file=sys.stderr)
    for key in sorted(summary):
        print(f"  {key}: {summary[key]}", file=sys.stderr)
    print(f"CSV geschrieben: {output}", file=sys.stderr)

    if args.upload:
        print("", file=sys.stderr)
        print("Upload-Zusammenfassung", file=sys.stderr)
        print(f"  hochgeladen: {upload_stats.uploaded}", file=sys.stderr)
        print(f"  übersprungen: {upload_stats.skipped}", file=sys.stderr)
        print(f"  Fehler:      {upload_stats.errors}", file=sys.stderr)
        for message in upload_stats.messages:
            print(f"  {message}", file=sys.stderr)

    return 0 if upload_stats.errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
