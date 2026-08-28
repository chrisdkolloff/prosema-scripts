"""Run ``alembic upgrade head`` with Azure App Service application settings.

Used by GitHub Actions. Loads a JSON list of ``{name, value}`` objects into
the process environment, then execs Alembic. Does not print secret values.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def apply_appsettings(settings: list[object]) -> None:
    for item in settings:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        value = item.get("value")
        os.environ[str(name)] = "" if value is None else str(value)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: alembic_upgrade_from_appsettings.py SETTINGS.json", file=sys.stderr)
        return 2
    path = Path(args[0])
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("expected a JSON list of {name, value} objects", file=sys.stderr)
        return 1
    apply_appsettings(raw)
    if not os.environ.get("DATABASE_URL", "").strip():
        print("DATABASE_URL missing from App Service settings", file=sys.stderr)
        return 1
    print("Running alembic upgrade head")
    return subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"])


if __name__ == "__main__":
    raise SystemExit(main())
