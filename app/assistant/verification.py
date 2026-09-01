"""Pure numeric-grounding check for German assistant answers."""

from __future__ import annotations

import re

# Article numbers first so 020.020.0010 is one token, not three.
_TOKEN_RE = re.compile(
    r"""
    \d{3}\.\d{3}\.\d{4}
    | \d{1,3}(?:'\d{3})+(?:[.,]\d+)?
    | \d+,\d+
    | \d+\.\d+
    | \d+
    """,
    re.VERBOSE,
)


def _interpretations(token: str) -> set[str]:
    """Plausible readings of one numeric token (notation, not arithmetic)."""
    variants = {token}
    stripped = token.replace("'", "").replace("\u2019", "")
    variants.add(stripped)
    if re.fullmatch(r"\d{3}\.\d{3}\.\d{4}", stripped):
        return variants
    if "." in stripped:
        variants.add(stripped.replace(".", ""))
    if "," in stripped:
        variants.add(stripped.replace(",", "."))
        if "." in stripped:
            variants.add(stripped.replace(".", "").replace(",", "."))
    return {item for item in variants if item}


def verify_numbers(answer_de: str, allowed: set[str]) -> tuple[bool, set[str]]:
    """Return whether every numeric token in ``answer_de`` is in ``allowed``.

    Callers build ``allowed`` from numbers in tool results, tool arguments, and
    the user question. A token matches if any plausible reading of it appears
    in ``allowed``: as written, apostrophes stripped, dots removed (German
    thousands), or comma taken as a decimal separator. Article numbers keep
    their dots. Verification is a fabrication guard, not a parser.
    """
    allowed_all: set[str] = set()
    for item in allowed:
        allowed_all.update(_interpretations(item))

    unaccounted: set[str] = set()
    for token in _TOKEN_RE.findall(answer_de or ""):
        if _interpretations(token) & allowed_all:
            continue
        unaccounted.add(token)
    return (not unaccounted, unaccounted)
