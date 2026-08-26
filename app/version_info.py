"""Load application version and changelog from ``releases.toml``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_RELEASES_PATH = Path(__file__).resolve().parent / "releases.toml"


@dataclass(frozen=True)
class Release:
    version: str
    date: str
    summary: str
    changes: tuple[str, ...]


@dataclass(frozen=True)
class VersionInfo:
    version: str
    releases: tuple[Release, ...]


def _parse_release(raw: dict[str, object]) -> Release:
    changes_raw = raw.get("changes", [])
    if not isinstance(changes_raw, list):
        raise ValueError("release changes must be a list of strings")
    changes = tuple(str(item) for item in changes_raw)
    return Release(
        version=str(raw["version"]),
        date=str(raw.get("date", "")),
        summary=str(raw.get("summary", "")),
        changes=changes,
    )


@lru_cache
def load_version_info() -> VersionInfo:
    data = tomllib.loads(_RELEASES_PATH.read_text(encoding="utf-8"))
    version = str(data["version"])
    releases_raw = data.get("releases", [])
    if not isinstance(releases_raw, list):
        raise ValueError("releases must be a list")
    releases = tuple(_parse_release(item) for item in releases_raw)
    return VersionInfo(version=version, releases=releases)
