"""Alt-text conventions for Shopify product images (source filename tracking)."""

from __future__ import annotations

ALT_SOURCE_PREFIX = "src:"


def media_alt_text(*, filename: str, article_number: str, kind: str) -> str:
    kind_label = "Farbfoto" if kind == "color" else "Strichzeichnung"
    return f"{ALT_SOURCE_PREFIX}{filename}|{article_number} – {kind_label}"


def parse_source_filename(alt: str | None) -> str | None:
    text = (alt or "").strip()
    if not text.startswith(ALT_SOURCE_PREFIX):
        return None
    rest = text[len(ALT_SOURCE_PREFIX) :]
    filename = rest.split("|", 1)[0].strip()
    return filename or None
