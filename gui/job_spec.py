"""Shared job specification types used by scripts and the GUI."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FieldKind(str, Enum):
    FILE_IN = "file_in"
    FILE_OUT = "file_out"
    BOOL = "bool"
    INT = "int"
    STR = "str"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: FieldKind
    default: Any
    help: str = ""
    advanced: bool = False
    output_name: str | None = None


@dataclass
class RunResult:
    summary: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JobSpec:
    id: str
    title: str
    description: str
    fields: tuple[FieldSpec, ...]
    run: Callable[[dict[str, Any]], RunResult]


def default_output_path(input_path: str | Path, output_name: str) -> Path:
    return Path(input_path).parent / output_name


def defaults_from_spec(spec: JobSpec) -> dict[str, Any]:
    return {f.name: f.default for f in spec.fields}


def coerce_params(spec: JobSpec, raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for fld in spec.fields:
        val = raw.get(fld.name, fld.default)
        if fld.kind == FieldKind.BOOL:
            result[fld.name] = bool(val)
        elif fld.kind == FieldKind.INT:
            if val == "" or val is None:
                result[fld.name] = fld.default
            else:
                result[fld.name] = int(val)
        elif fld.kind == FieldKind.STR:
            result[fld.name] = "" if val is None else str(val)
        else:
            result[fld.name] = "" if val is None else str(val)
    return result


def validate_params(spec: JobSpec, params: dict[str, Any]) -> None:
    for fld in spec.fields:
        if fld.kind == FieldKind.FILE_IN:
            path = Path(params[fld.name])
            if not path.exists():
                raise FileNotFoundError(f"Eingabedatei nicht gefunden: {path}")


def _cli_dest(field: FieldSpec) -> str:
    if field.kind == FieldKind.FILE_IN:
        return "input"
    if field.kind == FieldKind.FILE_OUT:
        return "output"
    return field.name


def build_argparser(spec: JobSpec) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=spec.description)
    for fld in spec.fields:
        dest = _cli_dest(fld)
        if fld.kind == FieldKind.FILE_IN:
            parser.add_argument(
                "input",
                nargs="?",
                default=fld.default,
                help=fld.help or fld.label,
            )
        elif fld.kind == FieldKind.FILE_OUT:
            parser.add_argument(
                "-o",
                "--output",
                dest="output",
                default=fld.default,
                help=fld.help or fld.label,
            )
        elif fld.kind == FieldKind.BOOL:
            parser.add_argument(
                f"--{fld.name.replace('_', '-')}",
                dest=dest,
                action=argparse.BooleanOptionalAction,
                default=fld.default,
                help=fld.help or fld.label,
            )
        elif fld.kind == FieldKind.INT:
            parser.add_argument(
                f"--{fld.name.replace('_', '-')}",
                dest=dest,
                type=int,
                default=fld.default,
                help=fld.help or fld.label,
            )
        elif fld.kind == FieldKind.STR:
            parser.add_argument(
                f"--{fld.name.replace('_', '-')}",
                dest=dest,
                default=fld.default,
                help=fld.help or fld.label,
            )
    return parser


def args_to_params(spec: JobSpec, args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for fld in spec.fields:
        dest = _cli_dest(fld)
        params[fld.name] = getattr(args, dest)
    return params
