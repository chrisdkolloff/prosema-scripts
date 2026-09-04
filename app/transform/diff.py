"""Server-side transform diffs. Standard-library SequenceMatcher only."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Literal

from markupsafe import Markup, escape

from app.transform.engine import _word_pattern
from core.article_write_fields import _TAG_RE, ValueKind, write_field

SegmentKind = Literal["equal", "deleted", "inserted"]

MSG_HTML_FORMAT = (
    "Enthält Formatierung, die beim Schreiben erhalten bleibt, hier aber nicht angezeigt wird."
)

_TAG_OR_EMPTY = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class DiffSegment:
    kind: SegmentKind
    text: str


def html_projection(value: str) -> str:
    """Tags-stripped text for display and diff. Does not unescape entities."""
    text = "" if value is None else str(value)
    return _TAG_OR_EMPTY.sub("", text)


def contains_markup(value: str) -> bool:
    text = "" if value is None else str(value)
    return bool(_TAG_RE.search(text))


def _opcodes_to_segments(before: str, after: str) -> list[DiffSegment]:
    from difflib import SequenceMatcher

    matcher = SequenceMatcher(a=before, b=after, autojunk=False)
    out: list[DiffSegment] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            if i1 != i2:
                out.append(DiffSegment("equal", before[i1:i2]))
        elif tag == "delete":
            if i1 != i2:
                out.append(DiffSegment("deleted", before[i1:i2]))
        elif tag == "insert":
            if j1 != j2:
                out.append(DiffSegment("inserted", after[j1:j2]))
        else:
            if i1 != i2:
                out.append(DiffSegment("deleted", before[i1:i2]))
            if j1 != j2:
                out.append(DiffSegment("inserted", after[j1:j2]))
    return _collapse(out)


def _collapse(segments: list[DiffSegment]) -> list[DiffSegment]:
    collapsed: list[DiffSegment] = []
    for segment in segments:
        if not segment.text:
            continue
        if collapsed and collapsed[-1].kind == segment.kind:
            collapsed[-1] = DiffSegment(segment.kind, collapsed[-1].text + segment.text)
        else:
            collapsed.append(segment)
    return collapsed


def _literal_segments(before: str, search: str, replacement: str) -> list[DiffSegment]:
    if not search:
        return [DiffSegment("equal", before)] if before else []
    out: list[DiffSegment] = []
    start = 0
    while True:
        i = before.find(search, start)
        if i < 0:
            if start < len(before):
                out.append(DiffSegment("equal", before[start:]))
            return _collapse(out)
        if i > start:
            out.append(DiffSegment("equal", before[start:i]))
        out.append(DiffSegment("deleted", search))
        if replacement:
            out.append(DiffSegment("inserted", replacement))
        start = i + len(search)


def _regex_segments(before: str, pattern, replacement: str) -> list[DiffSegment]:
    out: list[DiffSegment] = []
    pos = 0
    for match in pattern.finditer(before):
        if match.start() > pos:
            out.append(DiffSegment("equal", before[pos : match.start()]))
        out.append(DiffSegment("deleted", match.group(0)))
        if replacement:
            out.append(DiffSegment("inserted", replacement))
        pos = match.end()
    if pos < len(before):
        out.append(DiffSegment("equal", before[pos:]))
    return _collapse(out)


def _segments_for_step(before: str, item: dict) -> list[DiffSegment]:
    op = str(item.get("op") or "")
    search = str(item.get("search") or "")
    replacement = "" if op in {"remove_literal", "remove_word"} else str(item.get("replace") or "")
    if op in {"replace_word", "remove_word"}:
        return _regex_segments(before, _word_pattern(search), replacement)
    return _literal_segments(before, search, replacement)


def _project_if_html(text: str, *, html: bool) -> str:
    return html_projection(text) if html else ("" if text is None else str(text))


def segments_from_fired(
    old_value: str,
    new_value: str,
    operations_fired: list[dict],
    *,
    value_kind: ValueKind,
) -> list[DiffSegment]:
    """Diff from per-operation before/after, not a single old-vs-new pass."""
    html = value_kind is ValueKind.HTML
    steps: list[tuple[str, dict]] = []
    for item in operations_fired or []:
        before = item.get("before")
        after = item.get("after")
        if before is None or after is None:
            continue
        steps.append((_project_if_html(str(before), html=html), item))
    if not steps:
        return _opcodes_to_segments(
            _project_if_html(old_value, html=html),
            _project_if_html(new_value, html=html),
        )
    segments: list[DiffSegment] = []
    for i, (before, item) in enumerate(steps):
        if i:
            segments.append(DiffSegment("equal", "\n"))
        segments.extend(_segments_for_step(before, item))
    return _collapse(segments)


def render_diff_html(segments: list[DiffSegment]) -> Markup:
    parts: list[str] = []
    for segment in segments:
        escaped = escape(segment.text)
        if segment.kind == "deleted":
            parts.append(f'<del class="text-danger">{escaped}</del>')
        elif segment.kind == "inserted":
            parts.append(f'<ins class="text-success">{escaped}</ins>')
        else:
            parts.append(str(escaped))
    return Markup("".join(parts))


def field_is_html(snapshot_key: str) -> bool:
    return write_field(snapshot_key).value_kind is ValueKind.HTML


def escape_text(value: str) -> str:
    return html.escape("" if value is None else str(value), quote=True)
