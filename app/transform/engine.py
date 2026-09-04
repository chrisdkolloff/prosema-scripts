"""Pure transform engine. No I/O."""

from __future__ import annotations

import re

from app.transform.schemas import TransformOperation
from core.article_write_fields import (
    ValueKind,
    substitute_preserving_markup,
    transform_preserving_markup,
)

# Same boundaries as scripts/tmp/rename_winkelprofil.py VERBINDER:
# "verbinder" must not match inside "Eckverbinder" or "verbinder-set".
_WORD_GUARD = r"A-Za-zÄÖÜäöüß-"


def _word_pattern(search: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![{_WORD_GUARD}]){re.escape(search)}(?![{_WORD_GUARD}])",
        re.IGNORECASE,
    )


def _apply_word(text: str, search: str, replacement: str) -> str:
    return _word_pattern(search).sub(lambda _m: replacement, text)


def _apply_one_plain(value: str, operation: TransformOperation) -> str:
    if operation.op == "replace_literal":
        return value.replace(operation.search, operation.replace)
    if operation.op == "remove_literal":
        return value.replace(operation.search, "")
    if operation.op == "replace_word":
        return _apply_word(value, operation.search, operation.replace)
    return _apply_word(value, operation.search, "")


def _apply_one_html(value: str, operation: TransformOperation) -> str:
    if operation.op == "replace_literal":
        return substitute_preserving_markup(value, operation.search, operation.replace)
    if operation.op == "remove_literal":
        return substitute_preserving_markup(value, operation.search, "")
    if operation.op == "replace_word":
        return transform_preserving_markup(
            value, lambda segment: _apply_word(segment, operation.search, operation.replace)
        )
    return transform_preserving_markup(
        value, lambda segment: _apply_word(segment, operation.search, "")
    )


def apply_operations(
    value: str,
    operations: list[TransformOperation],
    value_kind: ValueKind,
) -> str:
    """Apply operations in list order. Unchanged if nothing matches."""
    text = "" if value is None else str(value)
    html = value_kind is ValueKind.HTML
    running = text
    for operation in operations:
        running = _apply_one_html(running, operation) if html else _apply_one_plain(running, operation)
    return running


def operations_fired(
    old: str,
    operations: list[TransformOperation],
    value_kind: ValueKind,
) -> list[dict[str, str]]:
    """Which operations changed the running value, in order."""
    fired: list[dict[str, str]] = []
    running = "" if old is None else str(old)
    html = value_kind is ValueKind.HTML
    for operation in operations:
        nxt = _apply_one_html(running, operation) if html else _apply_one_plain(running, operation)
        if nxt != running:
            item = {
                "op": operation.op,
                "search": operation.search,
                "before": running,
                "after": nxt,
            }
            if hasattr(operation, "replace"):
                item["replace"] = operation.replace
            fired.append(item)
        running = nxt
    return fired
