"""Bump ``app/releases.toml`` for a tools-site release."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
RELEASES_PATH = _ROOT / "app" / "releases.toml"
_VERSION_RE = re.compile(r"^version = \"([^\"]+)\"", re.MULTILINE)


def current_version(text: str) -> str:
    match = _VERSION_RE.search(text)
    if match is None:
        raise ValueError("releases.toml has no top-level version")
    return match.group(1)


def bump_version(version: str, part: str = "patch") -> str:
    bits = version.split(".")
    if len(bits) != 3 or not all(item.isdigit() for item in bits):
        raise ValueError(f"version must be N.N.N, got {version!r}")
    major, minor, patch = (int(item) for item in bits)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump part {part!r}")


def toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_commit_message(message: str) -> tuple[str, list[str]]:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "Release", ["Release"]
    summary = lines[0]
    changes = [line.lstrip("- ").strip() for line in lines[1:]]
    changes = [item for item in changes if item]
    if not changes:
        changes = [summary]
    return summary, changes


def render_release_block(
    *,
    version: str,
    date: str,
    summary: str,
    changes: list[str],
) -> str:
    lines = [
        f'version = "{version}"',
        "",
        "[[releases]]",
        f'version = "{version}"',
        f'date = "{date}"',
        f"summary = {toml_string(summary)}",
        "changes = [",
    ]
    for item in changes:
        lines.append(f"  {toml_string(item)},")
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def apply_bump(
    text: str,
    *,
    part: str = "patch",
    summary: str,
    changes: list[str],
    date: str | None = None,
) -> tuple[str, str, str]:
    old = current_version(text)
    new = bump_version(old, part)
    today = date or dt.date.today().isoformat()
    block = render_release_block(
        version=new,
        date=today,
        summary=summary,
        changes=changes,
    )
    updated, count = _VERSION_RE.subn(block.rstrip() + "\n", text, count=1)
    if count != 1:
        raise ValueError("could not replace top-level version in releases.toml")
    parsed = tomllib.loads(updated)
    if parsed["version"] != new:
        raise ValueError("bumped TOML did not parse with the new version")
    if not parsed["releases"] or parsed["releases"][0]["version"] != new:
        raise ValueError("new release entry is not first in the list")
    return updated, old, new


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump app/releases.toml")
    parser.add_argument("--print-next", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--part",
        choices=("patch", "minor", "major"),
        default="patch",
    )
    parser.add_argument("--message", default="")
    parser.add_argument(
        "--date",
        default="",
        help="ISO date (default: today)",
    )
    args = parser.parse_args()

    text = RELEASES_PATH.read_text(encoding="utf-8")
    old = current_version(text)
    new = bump_version(old, args.part)
    if args.print_next:
        print(f"{old} {new}")
        return 0

    if not args.write:
        parser.error("use --write or --print-next")

    summary, changes = parse_commit_message(args.message)
    updated, _, new = apply_bump(
        text,
        part=args.part,
        summary=summary,
        changes=changes,
        date=args.date or None,
    )
    RELEASES_PATH.write_text(updated, encoding="utf-8")
    print(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
