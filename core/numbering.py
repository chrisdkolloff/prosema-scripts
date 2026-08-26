"""
Artikelnummer-Vergabe (reine Logik, ohne Excel).

Format:  MMM.SSS.NNNN
  MMM  = Hauptgruppe
  SSS  = Unterartikelgruppe
  NNNN = laufende Nummer (eindeutig innerhalb jedes MMM.SSS)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Scheme:
    main_width: int = 3
    sub_width: int = 3
    running_width: int = 4  # "4 Dezimalstellen"; note mask said ZZZZZ (5)
    separator: str = "."
    start: int = 10
    step: int = 10

    @property
    def max_running(self) -> int:
        return 10 ** self.running_width - 1

    def normalize_group(self, value, width: int, where: str) -> str:
        raw = "" if value is None else str(value).strip()
        if raw == "":
            raise ValueError(f"Leerer Gruppencode in {where}.")
        if not raw.isdigit():
            raise ValueError(f"Ungültige Gruppe {raw!r} in {where} (nur Ziffern erlaubt).")
        if len(raw) > width:
            raise ValueError(f"Gruppe {raw!r} in {where} ist länger als {width} Stellen.")
        return f"{int(raw):0{width}d}"

    def format(self, main: str, sub: str, running: int) -> str:
        return f"{main}{self.separator}{sub}{self.separator}{running:0{self.running_width}d}"

    def pattern(self) -> re.Pattern[str]:
        s = re.escape(self.separator)
        return re.compile(
            rf"^(\d{{{self.main_width}}}){s}(\d{{{self.sub_width}}}){s}(\d{{{self.running_width}}})$"
        )


@dataclass
class RowResolutionError:
    row: int
    main_name: str | None = None
    sub_name: str | None = None
    main_unknown: bool = False
    sub_unknown: bool = False


@dataclass(frozen=True)
class RowInput:
    """One spreadsheet row as plain values for numbering."""

    row: int
    main_name: object | None
    sub_name: object | None
    existing_article_number: object | None
    is_data_row: bool = True


@dataclass(frozen=True)
class GroupDictionary:
    main_name_to_code: Mapping[str, str]
    sub_name_to_code: Mapping[tuple[str, str], str]


@dataclass
class AssignmentResult:
    """Outcome of assign_numbers.

    ``numbers`` maps every data row that kept or received a number to its
    final article number (existing kept or newly assigned). Rows skipped due
    to unresolved groups are omitted.
    ``assigned`` maps only rows that received a *new* number in this run.
    ``high_water`` maps ``"MMM.SSS"`` -> highest running number seen/issued.
    """

    numbers: dict[int, str] = field(default_factory=dict)
    assigned: dict[int, str] = field(default_factory=dict)
    high_water: dict[str, int] = field(default_factory=dict)
    errors: list[RowResolutionError] = field(default_factory=list)

    @property
    def assigned_count(self) -> int:
        return len(self.assigned)


def normalize_group_name(value) -> str:
    """Normalize a group name for lookup: strip whitespace, compare as lowercase."""
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize_group_code(value) -> str:
    """Normalize a group code from the dictionary: strip whitespace, lowercase."""
    if value is None:
        return ""
    return str(value).strip().lower()


def resolve_group_codes(
    *,
    row: int,
    main_raw,
    sub_raw,
    main_name_to_code: Mapping[str, str],
    sub_name_to_code: Mapping[tuple[str, str], str],
    scheme: Scheme,
) -> tuple[str | None, str | None, RowResolutionError | None]:
    main_name = normalize_group_name(main_raw)
    sub_name = normalize_group_name(sub_raw)
    main_display = main_name or None
    sub_display = sub_name or None

    err = RowResolutionError(row=row, main_name=main_display, sub_name=sub_display)
    main_code: str | None = None

    if main_name == "":
        err.main_unknown = True
    else:
        main_code = main_name_to_code.get(main_name)
        if main_code is None:
            err.main_unknown = True

    if sub_name == "":
        err.sub_unknown = True
    elif main_code is not None:
        sub_code = sub_name_to_code.get((main_code, sub_name))
        if sub_code is None:
            err.sub_unknown = True
        else:
            try:
                main = scheme.normalize_group(main_code, scheme.main_width, f"Zeile {row}, Hauptgruppe")
                sub = scheme.normalize_group(sub_code, scheme.sub_width, f"Zeile {row}, Untergruppe")
                return main, sub, None
            except ValueError as e:
                raise ValueError(f"Zeile {row}: {e}") from e
    else:
        err.sub_unknown = True

    return None, None, err


def format_resolution_errors(errors: list[RowResolutionError]) -> str:
    missing_mains = sorted({err.main_name for err in errors if err.main_unknown and err.main_name})
    missing_subs = sorted(
        {err.sub_name for err in errors if err.sub_unknown and not err.main_unknown and err.sub_name}
    )

    lines = ["Gruppennamen konnten nicht aufgelöst werden:"]
    if missing_mains:
        lines.append(f"\nUnbekannte Hauptgruppen ({len(missing_mains)}):")
        lines.extend(f"  - {name}" for name in missing_mains)
    if missing_subs:
        lines.append(f"\nUnbekannte Untergruppen ({len(missing_subs)}):")
        lines.extend(f"  - {name}" for name in missing_subs)

    lines.append(f"\nDetails ({len(errors)} Zeile(n)):")
    for err in errors:
        parts = [f"  Zeile {err.row}:"]
        if err.main_unknown:
            parts.append(f" unbekannte Hauptgruppe {err.main_name!r}")
        elif err.sub_unknown:
            parts.append(f" unbekannte Untergruppe {err.sub_name!r}")
        lines.append("".join(parts))
    lines.append(
        "\nBitte korrigieren Sie die Namen in der Eingabedatei oder ergänzen Sie den Gruppenschlüssel."
    )
    return "\n".join(lines)


def assign_numbers(
    rows: Sequence[RowInput],
    groups: GroupDictionary,
    scheme: Scheme,
    *,
    overwrite_existing: bool = False,
    strict: bool = True,
) -> AssignmentResult:
    """Two-pass article-number assignment (idempotent when overwrite_existing=False).

    Pass 1 registers already-valid numbers as high-water marks per (main, sub)
    so nothing is ever re-issued. Pass 2 fills only blanks (or all rows when
    overwriting), continuing past the existing high water mark by ``step``.
    """
    pattern = scheme.pattern()
    counters: dict[tuple[str, str], int] = {}

    # Pass 1: register already-assigned numbers so we never collide or re-issue.
    if not overwrite_existing:
        for row_in in rows:
            val = row_in.existing_article_number
            m = pattern.match(str(val).strip()) if val is not None else None
            if m:
                key = (m.group(1), m.group(2))
                counters[key] = max(counters.get(key, 0), int(m.group(3)))

    resolution_errors: list[RowResolutionError] = []
    resolved_codes: dict[int, tuple[str, str]] = {}

    for row_in in rows:
        if not row_in.is_data_row:
            continue
        main, sub, err = resolve_group_codes(
            row=row_in.row,
            main_raw=row_in.main_name,
            sub_raw=row_in.sub_name,
            main_name_to_code=groups.main_name_to_code,
            sub_name_to_code=groups.sub_name_to_code,
            scheme=scheme,
        )
        if err is not None:
            resolution_errors.append(err)
        else:
            resolved_codes[row_in.row] = (main, sub)

    if resolution_errors:
        details = format_resolution_errors(resolution_errors)
        if strict:
            raise ValueError(
                f"{len(resolution_errors)} Zeile(n) mit unbekannten Gruppennamen "
                f"(strict=True, Datei wurde nicht gespeichert).\n\n{details}"
            )

    result = AssignmentResult(errors=list(resolution_errors))

    # Pass 2: fill blanks (or overwrite).
    for row_in in rows:
        if not row_in.is_data_row:
            continue
        if row_in.row not in resolved_codes:
            continue

        existing = row_in.existing_article_number
        if not overwrite_existing and existing is not None and pattern.match(str(existing).strip()):
            result.numbers[row_in.row] = str(existing).strip()
            continue

        main, sub = resolved_codes[row_in.row]
        key = (main, sub)

        current = counters.get(key)
        nxt = scheme.start if current is None else current + scheme.step
        if nxt > scheme.max_running:
            raise OverflowError(
                f"Gruppe {main}.{sub} hat das Maximum {scheme.max_running:0{scheme.running_width}d} "
                f"in Zeile {row_in.row} überschritten. running_width erhöhen."
            )
        counters[key] = nxt
        number = scheme.format(main, sub, nxt)
        result.assigned[row_in.row] = number
        result.numbers[row_in.row] = number

    result.high_water = {f"{k[0]}.{k[1]}": v for k, v in sorted(counters.items())}
    return result
