"""Sync product images from a SharePoint folder to Shopify."""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.shopify.config import ShopifyConfig

from app.microsoft_graph import (
    DriveFileEntry,
    GraphError,
    download_drive_item,
    graph_error_user_message,
    list_folder_files,
    resolve_sharepoint_folder_url,
)
from app.shopify_media_alt import media_alt_text, parse_source_filename

logger = logging.getLogger(__name__)

# macOS duplicate: "010.010.0010-1 2.JPG" → treat as index 2 drawing
MACOS_DUP_RE = re.compile(
    r"^(?P<article>\d{3}\.\d{3}\.\d{4})-(?P<index>\d+)\s+\d+(?P<ext>\.[A-Za-z0-9]+)$"
)


@dataclass
class RemoteImageFile:
    filename: str
    article_number: str
    index: int
    kind: str
    entry: DriveFileEntry


@dataclass
class RemoteArticleImages:
    article_number: str
    files: list[RemoteImageFile] = field(default_factory=list)

    @property
    def ordered_files(self) -> list[RemoteImageFile]:
        return sorted(self.files, key=lambda item: (item.index, item.filename.lower()))


@dataclass
class SyncStats:
    products_considered: int = 0
    uploaded: int = 0
    skipped_existing: int = 0
    cleared: int = 0
    no_shopify_product: int = 0
    no_files_in_folder: int = 0
    errors: int = 0
    warnings: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def _ensure_scripts_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def normalize_image_filename(name: str) -> str | None:
    """Return canonical filename for parsing, or None if unsupported."""
    from scripts.shopify.images import parse_image_filename

    if parse_image_filename(name) is not None:
        return name
    match = MACOS_DUP_RE.match(name)
    if not match:
        return None
    index = int(match.group("index"))
    if index != 1:
        return None
    article = match.group("article")
    ext = match.group("ext")
    return f"{article}-2{ext}"


def parse_remote_filename(name: str) -> tuple[str, int] | None:
    from scripts.shopify.images import parse_image_filename

    canonical = normalize_image_filename(name) or name
    parsed = parse_image_filename(canonical)
    if parsed is None:
        return None
    return parsed


def build_remote_catalog(files: list[DriveFileEntry]) -> tuple[dict[str, RemoteArticleImages], list[str]]:
    catalog: dict[str, RemoteArticleImages] = {}
    ignored: list[str] = []
    for entry in files:
        parsed = parse_remote_filename(entry.name)
        if parsed is None:
            ignored.append(entry.name)
            continue
        article, index = parsed
        canonical_name = normalize_image_filename(entry.name) or entry.name
        kind = "color" if index == 1 else "drawing"
        bundle = catalog.setdefault(article, RemoteArticleImages(article_number=article))
        bundle.files.append(
            RemoteImageFile(
                filename=canonical_name,
                article_number=article,
                index=index,
                kind=kind,
                entry=entry,
            )
        )
    return catalog, ignored


def _filename_key(name: str) -> str:
    return name.casefold()


def _existing_filenames(media: list[dict[str, str]]) -> set[str]:
    names: set[str] = set()
    for item in media:
        parsed = parse_source_filename(item.get("alt"))
        if parsed:
            names.add(_filename_key(parsed))
    return names


def _upload_files(
    client,
    *,
    product_id: str,
    article_number: str,
    files: list[RemoteImageFile],
    download,
) -> None:
    if not files:
        return
    names = [item.filename for item in files]
    targets = client.staged_upload_targets_for_filenames(names)
    resource_urls: list[str] = []
    for item, target in zip(files, targets, strict=True):
        data = download(item.entry)
        resource_urls.append(
            client.upload_bytes_to_staged_target(item.filename, data, target)
        )
    media_inputs = []
    for item, resource_url in zip(files, resource_urls, strict=True):
        media_inputs.append(
            {
                "originalSource": resource_url,
                "mediaContentType": "IMAGE",
                "alt": media_alt_text(
                    filename=item.filename,
                    article_number=article_number,
                    kind=item.kind,
                ),
            }
        )
    client.product_create_media(product_id, media_inputs)


def _desired_order_keys(files: list[RemoteImageFile]) -> list[str]:
    return [_filename_key(item.filename) for item in files]


def _reorder_product_media(
    client,
    *,
    product_id: str,
    desired_files: list[RemoteImageFile],
    media: list[dict[str, str]],
) -> None:
    desired_keys = _desired_order_keys(desired_files)
    key_to_desired_index = {key: index for index, key in enumerate(desired_keys)}

    def sort_key(item: dict[str, str]) -> tuple[int, str]:
        parsed = parse_source_filename(item.get("alt"))
        if parsed and _filename_key(parsed) in key_to_desired_index:
            return (key_to_desired_index[_filename_key(parsed)], item["id"])
        return (len(desired_keys) + 1, item["id"])

    ordered = sorted(media, key=sort_key)
    moves = []
    for new_position, item in enumerate(ordered):
        moves.append({"id": item["id"], "newPosition": str(new_position)})
    if moves:
        client.product_reorder_media(product_id, moves)


def run_sharepoint_shopify_sync(
    *,
    sharepoint_url: str,
    replace_existing: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
    graph_token: str | None = None,
    shopify_config: ShopifyConfig | None = None,
) -> SyncStats:
    _ensure_scripts_path()
    from scripts.shopify.client import ShopifyClient, ShopifyError
    from scripts.shopify.config import load_config
    from scripts.shopify.images import product_from_shopify_node

    stats = SyncStats()

    try:
        folder = resolve_sharepoint_folder_url(sharepoint_url, token=graph_token)
        drive_files = list_folder_files(folder, token=graph_token, recursive=recursive)
    except GraphError as exc:
        stats.errors += 1
        stats.messages.append(graph_error_user_message(exc))
        return stats

    catalog, ignored = build_remote_catalog(drive_files)
    if ignored:
        preview = ", ".join(sorted(ignored)[:20])
        suffix = f" … (+{len(ignored) - 20})" if len(ignored) > 20 else ""
        stats.warnings.append(
            f"{len(ignored)} Dateiname(n) ignoriert (kein Artikelnummer-Muster): {preview}{suffix}"
        )

    if not catalog:
        stats.warnings.append("Im Ordner wurden keine gültigen Produktbilder gefunden.")
        return stats

    try:
        config = shopify_config or load_config()
        client = ShopifyClient(config)
    except (OSError, ValueError, ShopifyError) as exc:
        stats.errors += 1
        stats.messages.append(f"Shopify-Konfiguration: {exc}")
        return stats

    sku_to_product: dict[str, object] = {}
    for node in client.iter_products():
        ref = product_from_shopify_node(node)
        if ref is None:
            continue
        sku_to_product[ref.sku] = ref

    def download(entry: DriveFileEntry) -> bytes:
        return download_drive_item(entry, token=graph_token)

    articles_in_folder = sorted(catalog.keys())
    for article in articles_in_folder:
        bundle = catalog[article]
        product = sku_to_product.get(article)
        if product is None:
            stats.no_shopify_product += 1
            continue

        stats.products_considered += 1
        ordered = bundle.ordered_files
        if not ordered:
            stats.no_files_in_folder += 1
            continue

        if dry_run:
            stats.messages.append(
                f"DRY {article}: {len(ordered)} Datei(en) "
                f"({'ersetzen' if replace_existing else 'ergänzen'})"
            )
            continue

        try:
            if replace_existing:
                media_before = client.list_product_media(product.product_id)
                if media_before:
                    client.product_delete_media(
                        product.product_id,
                        [item["id"] for item in media_before],
                    )
                    stats.cleared += 1
                _upload_files(
                    client,
                    product_id=product.product_id,
                    article_number=article,
                    files=ordered,
                    download=download,
                )
                stats.uploaded += len(ordered)
                stats.messages.append(f"OK {article}: {len(ordered)} Bild(er) ersetzt")
                continue

            media = client.list_product_media(product.product_id)
            existing = _existing_filenames(media)
            to_upload = [
                item
                for item in ordered
                if _filename_key(item.filename) not in existing
            ]
            stats.skipped_existing += len(ordered) - len(to_upload)
            if to_upload:
                _upload_files(
                    client,
                    product_id=product.product_id,
                    article_number=article,
                    files=to_upload,
                    download=download,
                )
                stats.uploaded += len(to_upload)
            media_after = client.list_product_media(product.product_id)
            _reorder_product_media(
                client,
                product_id=product.product_id,
                desired_files=ordered,
                media=media_after,
            )
            if to_upload:
                stats.messages.append(
                    f"OK {article}: {len(to_upload)} neu, "
                    f"{len(ordered) - len(to_upload)} bereits vorhanden"
                )
            else:
                stats.messages.append(f"OK {article}: keine neuen Dateien")
        except ShopifyError as exc:
            stats.errors += 1
            stats.messages.append(f"FEHLER {article}: {exc}")

    return stats


def primary_error_detail(stats: SyncStats) -> str | None:
    for msg in stats.messages:
        text = msg.strip()
        if text.startswith(("FEHLER", "Shopify-Konfiguration")):
            return text
    for msg in stats.messages:
        text = msg.strip()
        if text:
            return text
    return None


def run_sync_job(
    payload: dict,
    *,
    shopify_config: ShopifyConfig | None = None,
    graph_token: str | None = None,
) -> dict:
    sharepoint_url = str(payload.get("sharepoint_url") or "").strip()
    replace_existing = bool(payload.get("replace_existing"))
    dry_run = bool(payload.get("dry_run"))
    recursive = bool(payload.get("recursive"))

    stats = run_sharepoint_shopify_sync(
        sharepoint_url=sharepoint_url,
        replace_existing=replace_existing,
        dry_run=dry_run,
        recursive=recursive,
        shopify_config=shopify_config,
        graph_token=graph_token,
    )

    mode = "Ersetzen" if replace_existing else "Ergänzen"
    if dry_run:
        mode = f"Vorschau ({mode})"

    summary = (
        f"{mode}: {stats.uploaded} hochgeladen, "
        f"{stats.skipped_existing} übersprungen (Dateiname bereits vorhanden), "
        f"{stats.products_considered} Artikel mit Bildern im Ordner, "
        f"{stats.no_shopify_product} ohne Shopify-Produkt, "
        f"{stats.errors} Fehler."
    )
    if stats.cleared:
        summary += f" {stats.cleared} Artikel mit gelöschten Altbildern."

    warning_cap = 50
    warnings = stats.warnings + stats.messages[-warning_cap:]
    error_detail = primary_error_detail(stats) if stats.errors else None
    return {
        "message": summary,
        "error_detail": error_detail,
        "uploaded": stats.uploaded,
        "skipped_existing": stats.skipped_existing,
        "products_considered": stats.products_considered,
        "no_shopify_product": stats.no_shopify_product,
        "errors": stats.errors,
        "warnings": warnings,
        "warning_count": len(stats.warnings) + len(stats.messages),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def job_failure_message(result: dict) -> str:
    detail = str(result.get("error_detail") or "").strip()
    summary = str(result.get("message") or "Synchronisation fehlgeschlagen").strip()
    if detail and detail != summary:
        return f"{detail}\n\n{summary}"
    return detail or summary
