"""Shell helper: work branch selection (dev vs dev-dk)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prosema_dev_branch.sh"


def _branch(*, extra_env: dict[str, str] | None = None) -> str:
    run_env = {"PROSEMA_REPO_ROOT": str(ROOT)}
    if extra_env:
        run_env.update(extra_env)
    out = subprocess.run(
        ["bash", "-c", f"source {SCRIPT} && prosema_dev_branch"],
        check=True,
        capture_output=True,
        text=True,
        env=run_env,
    )
    return out.stdout.strip()


def test_explicit_override():
    assert _branch(extra_env={"PROSEMA_DEV_BRANCH": "feature-x"}) == "feature-x"


def test_resolves_to_known_branch_name():
    assert _branch() in {"dev", "dev-dk"}
