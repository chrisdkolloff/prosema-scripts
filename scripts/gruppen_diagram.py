"""
Gruppenhierarchie aus gruppen.xlsx als interaktives Plotly-Diagramm erzeugen.

Liest die Tabellenblätter „Hauptgruppen“ und „Untergruppen“ und rendert eine
Sunburst-Ansicht: Hauptgruppen im Inneren, Untergruppen im äußeren Ring.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover - handled at runtime
    go = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Subgroup:
    main_code: str
    sub_code: str
    name: str


ROOT_ID = "root"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = _project_root() / p
    return p


def _ensure_project_root() -> None:
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _format_code(value) -> str:
    raw = "" if value is None else str(value).strip()
    if raw == "":
        return ""
    if not raw.isdigit():
        raise ValueError(f"Ungültiger Gruppencode: {raw!r}")
    return f"{int(raw):03d}"


def _label(code: str, name: str) -> str:
    if name:
        return f"{code} {name}"
    return code


def load_groups(path: Path) -> tuple[dict[str, str], list[Subgroup]]:
    if not path.exists():
        raise FileNotFoundError(f"Gruppenschlüssel nicht gefunden: {path}")

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if "Hauptgruppen" not in wb.sheetnames:
            raise ValueError('Gruppenschlüssel enthält kein Tabellenblatt "Hauptgruppen".')
        if "Untergruppen" not in wb.sheetnames:
            raise ValueError('Gruppenschlüssel enthält kein Tabellenblatt "Untergruppen".')

        main_groups: dict[str, str] = {}
        for code_raw, name_raw in wb["Hauptgruppen"].iter_rows(
            min_row=2, max_col=2, values_only=True
        ):
            code = _format_code(code_raw)
            if code == "":
                continue
            name = "" if name_raw is None else str(name_raw).strip()
            main_groups[code] = name

        subgroups: list[Subgroup] = []
        for main_raw, sub_raw, name_raw, *_ in wb["Untergruppen"].iter_rows(
            min_row=2, max_col=3, values_only=True
        ):
            main_code = _format_code(main_raw)
            sub_code = _format_code(sub_raw)
            if main_code == "" or sub_code == "":
                continue
            name = "" if name_raw is None else str(name_raw).strip()
            if name == "":
                raise ValueError(
                    f"Leere Untergruppen-Bezeichnung für {main_code}.{sub_code}."
                )
            subgroups.append(Subgroup(main_code, sub_code, name))

        return main_groups, subgroups
    finally:
        wb.close()


def build_figure(
    main_groups: dict[str, str],
    subgroups: list[Subgroup],
):
    by_main: dict[str, list[Subgroup]] = {}
    for subgroup in subgroups:
        by_main.setdefault(subgroup.main_code, []).append(subgroup)

    ids = [ROOT_ID]
    labels = ["Produktgruppen"]
    parents = [""]
    values = [len(subgroups)]

    for main_code in sorted(by_main):
        main_id = f"main_{main_code}"
        main_name = main_groups.get(main_code, "")
        ids.append(main_id)
        labels.append(_label(main_code, main_name))
        parents.append(ROOT_ID)
        values.append(len(by_main[main_code]))

        for subgroup in sorted(by_main[main_code], key=lambda s: s.sub_code):
            sub_id = f"sub_{main_code}_{subgroup.sub_code}"
            ids.append(sub_id)
            labels.append(_label(subgroup.sub_code, subgroup.name))
            parents.append(main_id)
            values.append(1)

    fig = go.Figure(
        go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            hovertext=labels,
            hovertemplate="<b>%{hovertext}</b><extra></extra>",
            hoverlabel=dict(namelength=-1),
        )
    )
    fig.update_layout(
        title="Haupt- und Untergruppen",
        width=1400,
        height=1400,
        margin=dict(t=50, l=10, r=10, b=10),
        uniformtext=dict(minsize=10, mode="hide"),
    )
    return fig


def _output_path(output: Path, fmt: str) -> Path:
    suffix = f".{fmt}"
    if output.suffix.lower() == suffix:
        return output
    return output.with_suffix(suffix)


def render_diagram(
    main_groups: dict[str, str],
    subgroups: list[Subgroup],
    output: Path,
    fmt: str,
) -> Path:
    if go is None:
        raise ImportError(
            "Das Paket 'plotly' ist nicht installiert. "
            "Bitte ausführen: pip install plotly"
        )

    fig = build_figure(main_groups, subgroups)
    output_file = _output_path(output, fmt)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        fig.write_html(str(output_file), include_plotlyjs="cdn")
        return output_file

    try:
        fig.write_image(str(output_file))
    except ValueError as exc:
        raise RuntimeError(
            f"Statisches Format {fmt!r} benötigt das Paket 'kaleido'. "
            "Bitte ausführen: pip install kaleido — oder HTML verwenden (-f html)."
        ) from exc

    return output_file


def build_argparser() -> argparse.ArgumentParser:
    root = _project_root()
    parser = argparse.ArgumentParser(
        description="Haupt- und Untergruppen aus gruppen.xlsx als Diagramm erzeugen.",
    )
    parser.add_argument(
        "-i",
        "--input",
        default=str(root / "data" / "gruppen.xlsx"),
        help="Gruppenschlüssel (.xlsx, Standard: data/gruppen.xlsx)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(root / "data" / "gruppen_diagram.html"),
        help="Ausgabedatei (Standard: data/gruppen_diagram.html)",
    )
    parser.add_argument(
        "-f",
        "--format",
        default="html",
        choices=("html", "png", "svg", "pdf"),
        help="Ausgabeformat (Standard: html; png/svg/pdf benötigen kaleido)",
    )
    return parser


def main() -> None:
    _ensure_project_root()
    args = build_argparser().parse_args()

    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)

    try:
        main_groups, subgroups = load_groups(input_path)
        output_file = render_diagram(main_groups, subgroups, output_path, args.format)
    except (FileNotFoundError, ValueError, ImportError, RuntimeError, OSError) as exc:
        sys.exit(f"Abbruch: {exc}")

    print(f"Fertig: {output_file}")
    print(f"  Hauptgruppen:  {len(main_groups)}")
    print(f"  Untergruppen:  {len(subgroups)}")


if __name__ == "__main__":
    main()
