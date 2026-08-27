"""Unit tests for release version bumps."""

from __future__ import annotations

from scripts.bump_releases_toml import apply_bump, bump_version, parse_commit_message


SAMPLE = """# header

version = "0.2.2"

[[releases]]
version = "0.2.2"
date = "2026-08-27"
summary = "Old summary"
changes = [
  "old change",
]
"""


def test_bump_patch_minor_major():
    assert bump_version("0.2.2", "patch") == "0.2.3"
    assert bump_version("0.2.2", "minor") == "0.3.0"
    assert bump_version("1.9.7", "major") == "2.0.0"


def test_parse_commit_message():
    summary, changes = parse_commit_message(
        "Fix export\n\n- Add column W\n- Skip empty rows\n"
    )
    assert summary == "Fix export"
    assert changes == ["Add column W", "Skip empty rows"]


def test_apply_bump_inserts_new_release_first():
    updated, old, new = apply_bump(
        SAMPLE,
        part="patch",
        summary="Ship groups",
        changes=["Create pair in weclapp"],
        date="2026-08-27",
    )
    assert old == "0.2.2"
    assert new == "0.2.3"
    assert 'version = "0.2.3"' in updated
    assert updated.index('version = "0.2.3"') < updated.index('version = "0.2.2"')
    assert 'summary = "Ship groups"' in updated
    assert '  "Create pair in weclapp",' in updated
    import tomllib

    parsed = tomllib.loads(updated)
    assert parsed["version"] == "0.2.3"
    assert parsed["releases"][0]["version"] == "0.2.3"
    assert parsed["releases"][1]["version"] == "0.2.2"
