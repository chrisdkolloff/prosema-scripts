"""Numeric grounding for German assistant answers."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.assistant.verification import verify_numbers
from app.snapshots import snapshot_timestamp_numerals


def test_all_numbers_accounted_for():
    allowed = {"4175", "5", "0.25", "010.020.0010"}
    ok, missing = verify_numbers(
        "Es gibt 4175 Artikel. 5 wiegen über 0,25 kg, darunter 010.020.0010.",
        allowed,
    )
    assert ok is True
    assert missing == set()


def test_apostrophe_thousands_matches_plain():
    ok, missing = verify_numbers("Insgesamt 4'175 Zeilen.", {"4175"})
    assert ok is True
    assert missing == set()


def test_dot_thousands_matches_plain():
    ok, missing = verify_numbers("Mit 2.311 Einträgen.", {"2311"})
    assert ok is True
    assert missing == set()


def test_dot_thousands_does_not_match_unrelated_counts():
    ok, missing = verify_numbers("Mit 5.311 Einträgen.", {"4175", "2311"})
    assert ok is False
    assert "5.311" in missing


def test_comma_decimal_matches_dot():
    ok, missing = verify_numbers("Schwerer als 2,5 kg.", {"2.5"})
    assert ok is True
    assert missing == set()


def test_unaccounted_tokens_returned():
    ok, missing = verify_numbers("Es gibt 99 Artikel und 12 Gruppen.", {"99"})
    assert ok is False
    assert "12" in missing
    assert "99" not in missing


def test_empty_answer():
    ok, missing = verify_numbers("", {"1"})
    assert ok is True
    assert missing == set()


def test_datenstand_single_digit_day_is_traceable():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.assistant.service import _collect_numbers
    from app.snapshots import snapshot_timestamp_numerals

    when = datetime(2026, 9, 2, 15, 59, tzinfo=ZoneInfo("Europe/Zurich"))
    allowed = snapshot_timestamp_numerals(when)
    assert "2" in allowed
    assert "9" in allowed
    assert "2026" in allowed
    ok, missing = verify_numbers(
        "Ich habe 4174 Artikel gefunden. Der Datenstand ist der 2. September 2026, 15:59 Uhr.",
        allowed | {"4174"},
    )
    assert missing == set()
    assert ok is True
    collected = _collect_numbers(when)
    assert "2" in collected
    prose_ok, prose_missing = verify_numbers("2. September 2026", collected)
    assert prose_ok is True
    assert prose_missing == set()
