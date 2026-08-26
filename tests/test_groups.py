"""Tests for core.groups dictionary parsing."""

from __future__ import annotations

import pytest

from core.groups import build_main_name_to_code, build_sub_name_to_code, parse_group_dictionary


def test_duplicate_hauptgruppe_raises():
    with pytest.raises(ValueError, match="Doppelte Hauptgruppen-Bezeichnung"):
        build_main_name_to_code(
            [
                ("100", "Dichtungen"),
                ("101", "Dichtungen"),
            ]
        )


def test_duplicate_untergruppe_within_main_raises():
    with pytest.raises(ValueError, match="Doppelte Untergruppen-Bezeichnung"):
        build_sub_name_to_code(
            [
                ("100", "010", "O-Ring"),
                ("100", "011", "O-Ring"),
            ]
        )


def test_same_untergruppe_name_under_different_main_ok():
    mapping = build_sub_name_to_code(
        [
            ("100", "010", "O-Ring"),
            ("200", "010", "O-Ring"),
        ]
    )
    assert mapping[("100", "o-ring")] == "010"
    assert mapping[("200", "o-ring")] == "010"


def test_parse_group_dictionary_skips_empty_rows():
    groups = parse_group_dictionary(
        main_entries=[
            ("100", "Dichtungen"),
            (None, "Ignored"),
            ("", ""),
        ],
        sub_entries=[
            ("100", "010", "O-Ring"),
            ("100", None, "Skip"),
        ],
    )
    assert groups.main_name_to_code == {"dichtungen": "100"}
    assert groups.sub_name_to_code == {("100", "o-ring"): "010"}
