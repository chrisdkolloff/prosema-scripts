"""Sunburst figure for the group registry.

Sizes wedges from live subgroup counts only. Parent values are derived from
the same child lists that populate the outer ring, so they cannot disagree.
"""

from __future__ import annotations

import plotly.graph_objects as go
from sqlalchemy.orm import Session

from app.groups_service import list_active_hauptgruppen, list_active_untergruppen
from app.models import Hauptgruppe, Untergruppe

ROOT_ID = "root"
DIV_ID = "gruppen-sunburst"
ROOT_COLOR = "#e7e5e4"
EMPTY_COLOR = "#d6d3d1"
INK = "#1c1917"
# Light qualitative fills so dark labels stay readable on every wedge.
HAUPT_COLORS = (
    "#93c5fd",
    "#86efac",
    "#fcd34d",
    "#f9a8d4",
    "#c4b5fd",
    "#67e8f9",
    "#fdba74",
    "#d8b4fe",
    "#bef264",
    "#fca5a5",
    "#5eead4",
    "#fde68a",
)


def _lighten(hex_color: str, amount: float = 0.42) -> str:
    raw = hex_color.removeprefix("#")
    red, green, blue = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    red = round(red + (255 - red) * amount)
    green = round(green + (255 - green) * amount)
    blue = round(blue + (255 - blue) * amount)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _label(code: str, name: str, *, empty: bool = False) -> str:
    text = f"{code} {name}".strip()
    if empty:
        return f"{text} (leer)"
    return text


def load_active_group_tree(db: Session) -> list[tuple[Hauptgruppe, list[Untergruppe]]]:
    groups = list_active_hauptgruppen(db)
    return [(group, list_active_untergruppen(db, group.id)) for group in groups]


def build_sunburst_figure(
    tree: list[tuple[Hauptgruppe, list[Untergruppe]]],
) -> go.Figure:
    ids: list[str] = [ROOT_ID]
    labels: list[str] = ["Produktgruppen"]
    parents: list[str] = [""]
    values: list[int] = [0]
    customdata: list[list[str]] = [["", "", ""]]
    colors: list[str] = [ROOT_COLOR]
    shapes: list[str] = [""]
    root_total = 0

    for index, (hauptgruppe, untergruppen) in enumerate(tree):
        empty = not untergruppen
        # Empty groups would otherwise get value 0 and vanish. A synthetic 1
        # makes them visible at minimum width; they have no children, so the
        # branchvalues=total identity does not apply to them.
        hg_value = len(untergruppen) if untergruppen else 1
        root_total += hg_value
        hg_id = str(hauptgruppe.id)
        hg_color = EMPTY_COLOR if empty else HAUPT_COLORS[index % len(HAUPT_COLORS)]
        ids.append(hg_id)
        labels.append(_label(hauptgruppe.code, hauptgruppe.name, empty=empty))
        parents.append(ROOT_ID)
        values.append(hg_value)
        customdata.append([hg_id, "hauptgruppe", ""])
        colors.append(hg_color)
        shapes.append("/" if empty else "")
        for untergruppe in untergruppen:
            ug_id = str(untergruppe.id)
            ids.append(ug_id)
            labels.append(_label(untergruppe.code, untergruppe.name))
            parents.append(hg_id)
            values.append(1)
            customdata.append([ug_id, "untergruppe", hg_id])
            colors.append(_lighten(hg_color))
            shapes.append("")

    values[0] = root_total

    fig = go.Figure(
        go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            sort=False,
            customdata=customdata,
            hovertext=labels,
            hovertemplate="<b>%{hovertext}</b><extra></extra>",
            hoverlabel={"namelength": -1, "bgcolor": "#fff", "font": {"color": INK}},
            insidetextorientation="auto",
            insidetextfont={"color": INK, "size": 13},
            outsidetextfont={"color": INK, "size": 13},
            marker={
                "colors": colors,
                "line": {"color": "#fff", "width": 1.5},
                "pattern": {
                    "shape": shapes,
                    "solidity": 0.28,
                    "fgcolor": INK,
                    "fgopacity": 0.35,
                },
            },
        )
    )
    fig.update_layout(
        title=None,
        margin={"t": 0, "l": 0, "r": 0, "b": 0},
        # Draw every label at a readable size; the page script clips overflow
        # to the wedge and appends an ellipsis.
        uniformtext={"minsize": 10, "mode": "show"},
        height=1400,
        autosize=True,
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": INK},
    )
    return fig


def figure_html(fig: go.Figure) -> str:
    return fig.to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id=DIV_ID,
        config={"responsive": True, "displaylogo": False},
    )
