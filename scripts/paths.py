"""Shared path resolution for all PROSEMA scripts."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_PROCESSING = OUTPUT_DIR / "processing"
OUTPUT_EXPORT = OUTPUT_DIR / "export"
OUTPUT_REPORTS = OUTPUT_DIR / "reports"
OUTPUT_SHOPIFY = OUTPUT_DIR / "shopify"


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def ensure_parent_dir(path: str | Path) -> Path:
    resolved = resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_project_root_in_path() -> None:
    import sys

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
