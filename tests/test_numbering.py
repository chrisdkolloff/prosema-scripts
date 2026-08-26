"""Tests for core.numbering — no Excel fixtures required."""

from __future__ import annotations

import pytest

from core.numbering import (
    GroupDictionary,
    RowInput,
    Scheme,
    assign_numbers,
    resolve_group_codes,
)


def _groups() -> GroupDictionary:
    return GroupDictionary(
        main_name_to_code={
            "dichtungen": "100",
            "profile": "200",
        },
        sub_name_to_code={
            ("100", "o-ring"): "010",
            ("100", "flach"): "020",
            ("200", "u-profil"): "010",  # same sub code under different main
        },
    )


def _scheme(**kwargs) -> Scheme:
    return Scheme(**kwargs)


def test_idempotency_second_run_assigns_nothing():
    groups = _groups()
    scheme = _scheme()
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", None),
        RowInput(3, "Dichtungen", "O-Ring", None),
    ]
    first = assign_numbers(rows, groups, scheme, overwrite_existing=False, strict=True)
    assert first.assigned_count == 2
    assert first.assigned[2] == "100.010.0010"
    assert first.assigned[3] == "100.010.0020"

    second_rows = [
        RowInput(2, "Dichtungen", "O-Ring", first.numbers[2]),
        RowInput(3, "Dichtungen", "O-Ring", first.numbers[3]),
    ]
    second = assign_numbers(second_rows, groups, scheme, overwrite_existing=False, strict=True)
    assert second.assigned_count == 0
    assert second.numbers[2] == first.numbers[2]
    assert second.numbers[3] == first.numbers[3]


def test_per_group_counter_isolation():
    groups = _groups()
    scheme = _scheme()
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", None),
        RowInput(3, "Profile", "U-Profil", None),
        RowInput(4, "Dichtungen", "O-Ring", None),
        RowInput(5, "Profile", "U-Profil", None),
    ]
    result = assign_numbers(rows, groups, scheme)
    assert result.assigned[2] == "100.010.0010"
    assert result.assigned[3] == "200.010.0010"
    assert result.assigned[4] == "100.010.0020"
    assert result.assigned[5] == "200.010.0020"


def test_continuation_past_existing_including_noncontiguous_out_of_order():
    groups = _groups()
    scheme = _scheme()
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", "100.010.0030"),
        RowInput(3, "Dichtungen", "O-Ring", "100.010.0010"),  # lower, out of order
        RowInput(4, "Dichtungen", "O-Ring", None),
    ]
    result = assign_numbers(rows, groups, scheme, overwrite_existing=False)
    assert result.assigned_count == 1
    assert result.assigned[4] == "100.010.0040"
    assert result.numbers[2] == "100.010.0030"
    assert result.numbers[3] == "100.010.0010"


def test_blanks_only_when_overwrite_false():
    groups = _groups()
    scheme = _scheme()
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", "100.010.0010"),
        RowInput(3, "Dichtungen", "O-Ring", None),
    ]
    result = assign_numbers(rows, groups, scheme, overwrite_existing=False)
    assert 2 not in result.assigned
    assert result.numbers[2] == "100.010.0010"
    assert result.assigned[3] == "100.010.0020"


def test_overflow_raises():
    groups = _groups()
    scheme = _scheme(start=10, step=10)  # max_running == 9999
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", "100.010.9990"),
        RowInput(3, "Dichtungen", "O-Ring", None),
    ]
    with pytest.raises(OverflowError, match="Maximum 9999"):
        assign_numbers(rows, groups, scheme, overwrite_existing=False)


def test_malformed_group_codes_raise_german():
    scheme = _scheme()
    groups = GroupDictionary(
        main_name_to_code={"bad": "abc"},
        sub_name_to_code={("abc", "x"): "1"},
    )
    with pytest.raises(ValueError, match="nur Ziffern erlaubt"):
        resolve_group_codes(
            row=5,
            main_raw="Bad",
            sub_raw="X",
            main_name_to_code=groups.main_name_to_code,
            sub_name_to_code=groups.sub_name_to_code,
            scheme=scheme,
        )

    groups_long = GroupDictionary(
        main_name_to_code={"long": "1234"},
        sub_name_to_code={("1234", "x"): "1"},
    )
    with pytest.raises(ValueError, match="länger als 3 Stellen"):
        resolve_group_codes(
            row=6,
            main_raw="Long",
            sub_raw="X",
            main_name_to_code=groups_long.main_name_to_code,
            sub_name_to_code=groups_long.sub_name_to_code,
            scheme=scheme,
        )

    groups_empty = GroupDictionary(
        main_name_to_code={"empty": ""},
        sub_name_to_code={("", "x"): "1"},
    )
    with pytest.raises(ValueError, match="Leerer Gruppencode"):
        resolve_group_codes(
            row=7,
            main_raw="Empty",
            sub_raw="X",
            main_name_to_code=groups_empty.main_name_to_code,
            sub_name_to_code=groups_empty.sub_name_to_code,
            scheme=scheme,
        )


def test_unknown_groups_strict_raises_and_assigns_nothing():
    groups = _groups()
    scheme = _scheme()
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", None),
        RowInput(3, "Unbekannt", "O-Ring", None),
    ]
    with pytest.raises(ValueError, match="unbekannten Gruppennamen"):
        assign_numbers(rows, groups, scheme, strict=True)


def test_unknown_groups_non_strict_skips_but_assigns_resolvable():
    groups = _groups()
    scheme = _scheme()
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", None),
        RowInput(3, "Unbekannt", "O-Ring", None),
        RowInput(4, "Dichtungen", "Flach", None),
    ]
    result = assign_numbers(rows, groups, scheme, strict=False)
    assert result.assigned[2] == "100.010.0010"
    assert 3 not in result.assigned
    assert 3 not in result.numbers
    assert result.assigned[4] == "100.020.0010"
    assert len(result.errors) == 1
    assert result.errors[0].row == 3
    assert result.errors[0].main_unknown


def test_sub_unique_within_main_not_globally():
    """Same Untergruppe Bezeichnung under different Hauptgruppen is allowed."""
    groups = _groups()
    scheme = _scheme()
    rows = [
        RowInput(2, "Dichtungen", "O-Ring", None),
        RowInput(3, "Profile", "U-Profil", None),
    ]
    result = assign_numbers(rows, groups, scheme)
    assert result.assigned[2].startswith("100.010.")
    assert result.assigned[3].startswith("200.010.")
