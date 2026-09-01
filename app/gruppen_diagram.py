"""Group-registry diagram: query plus sunburst arc geometry."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.groups_service import list_active_hauptgruppen, list_active_untergruppen
from app.models import Hauptgruppe, Untergruppe

CX = 360.0
CY = 360.0
INNER_R = (80.0, 205.0)
OUTER_R = (212.0, 345.0)
PAD_IN = 8.0
PAD_OUT = 10.0
CHAR_W = 0.6
INNER_FONT = 13.0
OUTER_FONT = 10.0
MIN_ARC_DEG = 3.0


def load_active_group_tree(db: Session) -> list[tuple[Hauptgruppe, list[Untergruppe]]]:
    groups = list_active_hauptgruppen(db)
    return [(group, list_active_untergruppen(db, group.id)) for group in groups]


def build_sunburst_arcs(
    tree: list[tuple[Any, list[Any]]],
) -> list[dict[str, Any]]:
    """Return annular-sector dicts for the Gruppendiagramm SVG.

    ``tree`` is ``(hauptgruppe, untergruppen)`` as from ``load_active_group_tree``.
    Objects need ``.code`` and ``.name``; Hauptgruppen also need ``.id``.
    Untergruppen need ``.id`` for the detail-page fragment.
    """
    n = len(tree)
    total = sum(max(len(ugs), 1) for _, ugs in tree)
    if n == 0 or total == 0:
        return []

    arcs: list[dict[str, Any]] = []
    angle = -math.pi / 2
    for index, (hg, ugs) in enumerate(tree):
        span = 2 * math.pi * max(len(ugs), 1) / total
        a0 = angle
        a1 = angle + span
        hue = index * 360 / n
        child_count = len(ugs)
        child_context = german_count(child_count, "Untergruppe", "Untergruppen")
        arcs.append(
            _arc(
                ring="inner",
                r_in=INNER_R[0],
                r_out=INNER_R[1],
                a0=a0,
                a1=a1,
                fill=_hsl(hue, 55, 45),
                code=hg.code,
                name=hg.name,
                title=f"{hg.code} {hg.name} · {child_context}",
                href=f"/gruppen/{hg.id}",
                context=child_context,
                font_size=INNER_FONT,
            )
        )
        if ugs:
            ug_span = span / len(ugs)
            u0 = a0
            parent_label = f"{hg.code} {hg.name}".strip()
            for child_index, ug in enumerate(ugs):
                u1 = u0 + ug_span
                lightness = min(62 + child_index * 4, 80)
                arcs.append(
                    _arc(
                        ring="outer",
                        r_in=OUTER_R[0],
                        r_out=OUTER_R[1],
                        a0=u0,
                        a1=u1,
                        fill=_hsl(hue, 45, lightness),
                        code=ug.code,
                        name=ug.name,
                        title=f"{ug.code} {ug.name}".strip(),
                        href=f"/gruppen/{hg.id}#untergruppe-{ug.id}",
                        context=parent_label,
                        font_size=OUTER_FONT,
                    )
                )
                u0 = u1
        angle = a1
    return arcs


def german_count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def usable_length(r_in: float, r_out: float) -> float:
    return (r_out - r_in) - PAD_IN - PAD_OUT


def max_chars_for(r_in: float, r_out: float, font_size: float) -> int:
    return int(usable_length(r_in, r_out) / (font_size * CHAR_W))


def _hsl(hue: float, saturation: float, lightness: float) -> str:
    return f"hsl({hue:.2f}, {saturation:.0f}%, {lightness:.0f}%)"


def _choose_label(
    code: str, name: str, span: float, r_in: float, r_out: float, font_size: float
) -> tuple[str, str]:
    if math.degrees(span) <= MIN_ARC_DEG:
        return "none", ""
    budget = max_chars_for(r_in, r_out, font_size)
    full = f"{code} {name}"
    if len(full) <= budget:
        return "full", full
    keep = budget - len(code) - 2  # space + ellipsis
    if keep >= 3:
        stub = name[:keep].rstrip()
        if stub:
            return "full", f"{code} {stub}…"
    return "full", code


def _arc(
    *,
    ring: str,
    r_in: float,
    r_out: float,
    a0: float,
    a1: float,
    fill: str,
    code: str,
    name: str,
    title: str,
    href: str | None,
    context: str,
    font_size: float,
) -> dict[str, Any]:
    mid = (a0 + a1) / 2
    deg = math.degrees(mid)
    flip = 90 < (deg % 360) < 270
    rot = deg + 180 if flip else deg
    # Right half: start at the inner pad, run outward.
    # Left half: after the 180° flip, +x points inward — start at the outer
    # pad and run inward so short labels sit inside the band, not past r_out.
    r_anchor = (r_out - PAD_OUT) if flip else (r_in + PAD_IN)
    text_anchor = "start"
    mode, label = _choose_label(code, name, a1 - a0, r_in, r_out, font_size)
    x = CX + r_anchor * math.cos(mid)
    y = CY + r_anchor * math.sin(mid)
    return {
        "d": _annulus_path(r_in, r_out, a0, a1),
        "fill": fill,
        "code": code,
        "name": name,
        "label": label,
        "label_transform": (
            f"translate({round(x, 2)},{round(y, 2)}) rotate({round(rot, 2)})"
        ),
        "text_anchor": text_anchor,
        "show_label": mode != "none",
        "label_mode": mode,
        "title": title,
        "href": href,
        "context": context,
        "ring": ring,
        "a0": a0,
        "a1": a1,
    }


def _annulus_path(r_in: float, r_out: float, a0: float, a1: float) -> str:
    x0, y0 = CX + r_out * math.cos(a0), CY + r_out * math.sin(a0)
    x1, y1 = CX + r_out * math.cos(a1), CY + r_out * math.sin(a1)
    x2, y2 = CX + r_in * math.cos(a1), CY + r_in * math.sin(a1)
    x3, y3 = CX + r_in * math.cos(a0), CY + r_in * math.sin(a0)
    large = 1 if (a1 - a0) > math.pi else 0
    return (
        f"M {x0:.2f} {y0:.2f} A {r_out:.2f} {r_out:.2f} 0 {large} 1 {x1:.2f} {y1:.2f} "
        f"L {x2:.2f} {y2:.2f} A {r_in:.2f} {r_in:.2f} 0 {large} 0 {x3:.2f} {y3:.2f} Z"
    )
