"""Word-position of literal matches: standalone vs inside a compound."""

from __future__ import annotations

import re
from collections import defaultdict

from app.transform.engine import apply_operations
from app.transform.schemas import TransformOperation
from core.article_write_fields import _TAG_RE, ValueKind

# Same class as engine word guards: letters plus hyphen.
# Hyphenated forms (winkel-abschlussprofil) are compounds, not standalone.
_WORD_CHAR = re.compile(r"[A-Za-zÄÖÜäöüß-]")


def _is_embedded(text: str, start: int, end: int) -> bool:
    prev = text[start - 1] if start > 0 else ""
    nxt = text[end] if end < len(text) else ""
    return bool(
        (prev and _WORD_CHAR.match(prev)) or (nxt and _WORD_CHAR.match(nxt))
    )


def _plain_sites(text: str, search: str) -> list[bool]:
    if not search:
        return []
    embedded: list[bool] = []
    start = 0
    while True:
        i = text.find(search, start)
        if i < 0:
            return embedded
        embedded.append(_is_embedded(text, i, i + len(search)))
        start = i + max(len(search), 1)


def _html_sites(text: str, search: str) -> list[bool]:
    sites: list[bool] = []
    for piece in _TAG_RE.split(text):
        if piece.startswith("<") and piece.endswith(">") and len(piece) >= 2:
            continue
        sites.extend(_plain_sites(piece, search))
    return sites


def literal_match_embedded(
    value: str,
    search: str,
    value_kind: ValueKind,
) -> list[bool]:
    """For each case-sensitive literal match, True if inside a compound."""
    text = "" if value is None else str(value)
    if value_kind is ValueKind.HTML:
        return _html_sites(text, search)
    return _plain_sites(text, search)


class WordPositionCollector:
    def __init__(self, operations: list[TransformOperation]) -> None:
        self._ops = [
            op for op in operations if op.op in {"replace_literal", "remove_literal"}
        ]
        self.standalone = 0
        self.embedded = 0
        self.per_op: dict[str, dict[str, int]] = defaultdict(
            lambda: {"standalone": 0, "embedded": 0}
        )

    def observe_row(
        self, value: str, value_kind: ValueKind
    ) -> bool | None:
        """Return True if any literal match on this value is compound-internal.

        None when no literal match fired.
        """
        any_embedded = False
        any_match = False
        running = "" if value is None else str(value)

        for operation in self._ops:
            sites = literal_match_embedded(running, operation.search, value_kind)
            if sites:
                any_match = True
                for is_emb in sites:
                    bucket = "embedded" if is_emb else "standalone"
                    self.per_op[operation.search][bucket] += 1
                    if is_emb:
                        self.embedded += 1
                        any_embedded = True
                    else:
                        self.standalone += 1
            nxt = apply_operations(running, [operation], value_kind)
            running = nxt
        if not any_match:
            return None
        return any_embedded

    def payload(self) -> dict[str, object]:
        return {
            "standalone": self.standalone,
            "embedded": self.embedded,
            "by_search": [
                {
                    "search": search,
                    "standalone": counts["standalone"],
                    "embedded": counts["embedded"],
                }
                for search, counts in self.per_op.items()
            ],
        }
