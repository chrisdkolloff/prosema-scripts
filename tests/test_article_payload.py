"""weclapp create-payload defaults, especially Steuersatz."""

from __future__ import annotations

import pytest

from core.article_payload import coerce_tax_rate, resolve_tax_rate, row_to_payload
from scripts.weclapp.article_import import LookupTables, _load_schema


def _row(**extra: str) -> dict[str, str]:
    data = {
        "Prosema-Artikelnummer": "010.010.0010",
        "Prosema-Artikelname": "Testartikel",
        "Einheit": "Stk.",
    }
    data.update(extra)
    return data


def test_coerce_tax_rate_empty_and_normal_become_standard():
    assert coerce_tax_rate("") == "STANDARD"
    assert coerce_tax_rate(None) == "STANDARD"
    assert coerce_tax_rate("   ") == "STANDARD"
    assert coerce_tax_rate("normal") == "STANDARD"
    assert coerce_tax_rate("Normal") == "STANDARD"
    assert coerce_tax_rate("NORMAL") == "STANDARD"
    assert coerce_tax_rate("STANDARD") == "STANDARD"
    assert coerce_tax_rate("reduced") == "REDUCED"


def test_resolve_tax_rate_rejects_unknown():
    with pytest.raises(ValueError, match="Ungültiger Steuersatz"):
        resolve_tax_rate("foo")


def test_row_to_payload_empty_steuersatz_is_standard():
    lookups = LookupTables(_load_schema())
    payload = row_to_payload(_row(), lookups)
    assert payload["taxRateType"] == "STANDARD"
    payload = row_to_payload(_row(Steuersatz=""), lookups)
    assert payload["taxRateType"] == "STANDARD"
    payload = row_to_payload(_row(Steuersatz="normal"), lookups)
    assert payload["taxRateType"] == "STANDARD"
