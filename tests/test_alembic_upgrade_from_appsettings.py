"""App Service settings loader for production Alembic upgrades."""

from __future__ import annotations

import json
import os

from scripts.alembic_upgrade_from_appsettings import apply_appsettings, main


def test_apply_appsettings_sets_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    apply_appsettings(
        [
            {"name": "DATABASE_URL", "value": "postgresql+psycopg://example/db"},
            {"name": "ENVIRONMENT", "value": "production"},
        ]
    )
    assert os.environ["DATABASE_URL"] == "postgresql+psycopg://example/db"
    assert os.environ["ENVIRONMENT"] == "production"


def test_main_fails_without_database_url(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "settings.json"
    path.write_text(json.dumps([{"name": "ENVIRONMENT", "value": "production"}]), encoding="utf-8")
    assert main([str(path)]) == 1
    assert "DATABASE_URL missing" in capsys.readouterr().err
