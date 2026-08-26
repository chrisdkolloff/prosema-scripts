"""Tests for application version and changelog loading."""

from __future__ import annotations

from app.version_info import load_version_info


def test_load_version_info():
    info = load_version_info()
    assert info.version
    assert info.releases
    assert info.releases[0].version == info.version
    assert info.releases[0].changes
