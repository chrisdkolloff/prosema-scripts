"""Unit tests for the article update allowlist and PUT builder."""

from __future__ import annotations

from typing import Any

import pytest

from core.article_write_fields import (
    SNAPSHOT_INVENTORY_KEYS,
    WRITE_FIELDS,
    AmbiguousAttributeLabelError,
    CustomAttributeResolver,
    Location,
    ValueKind,
    Writability,
    build_article_put,
    pass_1_fields,
    substitute_preserving_markup,
    write_field,
)

# Prompt 1 inventory of keys on the latest complete prosema snapshot (4175 rows).
PROMPT_1_SNAPSHOT_KEYS = frozenset(
    {
        "Aktiv",
        "Artikelbeschreibung HTML",
        "Artikeltyp",
        "Bestand übertragen",
        "Bodenleger",
        "Breite in mm",
        "Dachdecker",
        "Einheit",
        "Einkaufspreis EUR netto",
        "Farbe",
        "Gewichtseinheit",
        "Grundmaterial",
        "GTIN (EAN-Nummer)",
        "Hauptgruppe",
        "Höhe in mm",
        "Im Shop aktiv",
        "Im Shop verfügbar",
        "Im Verkauf",
        "Kategorie",
        "Kurzbeschreibung",
        "Landschaftsgärtner",
        "Länge in cm",
        "Lieferanten Firmenname",
        "Lieferantenartikelnummer",
        "Lieferantennummer",
        "Nettogewicht kg",
        "Oberfläche",
        "Plattenleger",
        "Produkt-ID (Prosema)",
        "Produktfamilie",
        "Prosema-Artikelname",
        "Prosema-Artikelnummer",
        "Prosema-Langtext",
        "Rabattcode",
        "Referenz (Matchcode)",
        "Steuersatz",
        "Untergruppe",
        "Varianten-ID (Prosema)",
        "Verkaufseinheit",
        "Verkaufspreis €, BE",
        "Verpackung",
        "VPE 1",
        "VPE 2",
        "VPE 3",
        "weclapp Artikel-ID",
        "weclapp Bezugsquelle-ID",
        "weclapp Breite (m)",
        "weclapp Einheit-ID",
        "weclapp Erstellt am",
        "weclapp Geändert am",
        "weclapp Kategorie-ID",
        "weclapp Version",
        "Zolltarifnummer",
    }
)


class FakeWeclappClient:
    def __init__(self, definitions: list[dict[str, Any]]) -> None:
        self.definitions = definitions
        self.calls: list[tuple[str, int | None]] = []

    def iter_pages(self, entity: str, *, params=None, page_size=None):
        self.calls.append((entity, page_size))
        yield from self.definitions


def _defs(*rows: tuple[str, str]) -> list[dict[str, Any]]:
    return [{"id": attr_id, "label": label} for attr_id, label in rows]


def _pass1_string_defs() -> list[dict[str, Any]]:
    labels = [
        "Grundmaterial",
        "Oberfläche",
        "Farbe",
        "Produktfamilie",
        "Rabattcode",
        "Verkaufseinheit",
        "Verpackung",
        "VPE 1",
        "VPE 2",
        "VPE 3",
        "Breite in mm",
        "Höhe in mm",
        "Länge in cm",
        "Gewichtseinheit",
        "Produkt-ID (Prosema)",
        "Varianten-ID (Prosema)",
    ]
    return _defs(*((str(1000 + i), label) for i, label in enumerate(labels)))


def test_inventory_has_53_keys():
    assert len(PROMPT_1_SNAPSHOT_KEYS) == 53
    assert set(SNAPSHOT_INVENTORY_KEYS) == PROMPT_1_SNAPSHOT_KEYS


def test_catalogue_classifies_every_inventory_key():
    classified = {field.snapshot_key for field in WRITE_FIELDS}
    missing = PROMPT_1_SNAPSHOT_KEYS - classified
    assert missing == set()
    for key in PROMPT_1_SNAPSHOT_KEYS:
        field = write_field(key)
        assert field.writability in Writability
        assert field.location in Location
        assert field.value_kind in ValueKind


def test_unknown_key_raises():
    with pytest.raises(KeyError, match="not-a-column"):
        write_field("not-a-column")


def test_pass_1_fields_are_the_allowlist():
    keys = {field.snapshot_key for field in pass_1_fields()}
    assert keys == {
        "Prosema-Artikelname",
        "Prosema-Langtext",
        "Kurzbeschreibung",
        "Referenz (Matchcode)",
        "Grundmaterial",
        "Oberfläche",
        "Farbe",
        "Produktfamilie",
        "Rabattcode",
        "Verkaufseinheit",
        "Verpackung",
        "VPE 1",
        "VPE 2",
        "VPE 3",
        "Breite in mm",
        "Höhe in mm",
        "Länge in cm",
        "Gewichtseinheit",
        "Produkt-ID (Prosema)",
        "Varianten-ID (Prosema)",
    }


def test_forbidden_and_later_rejected_by_payload_builder():
    resolver = CustomAttributeResolver(FakeWeclappClient(_pass1_string_defs()))
    for key in (
        "Prosema-Artikelnummer",
        "Hauptgruppe",
        "Untergruppe",
        "Kategorie",
        "lowLevelCode",
        "weclapp Artikel-ID",
    ):
        with pytest.raises(ValueError, match=key):
            build_article_put("353023", "11", resolver, {key: "x"})
    for key in ("Aktiv", "Im Verkauf", "Einheit", "Artikeltyp", "Steuersatz", "Nettogewicht kg"):
        with pytest.raises(ValueError, match=key):
            build_article_put("353023", "11", resolver, {key: "x"})


def test_missing_version_raises():
    resolver = CustomAttributeResolver(FakeWeclappClient(_pass1_string_defs()))
    with pytest.raises(ValueError, match="version"):
        build_article_put("353023", "", resolver, {"Prosema-Artikelname": "x"})
    with pytest.raises(ValueError, match="version"):
        build_article_put("353023", None, resolver, {"Prosema-Artikelname": "x"})  # type: ignore[arg-type]


def test_sparse_custom_attribute_array_and_params():
    resolver = CustomAttributeResolver(FakeWeclappClient(_pass1_string_defs()))
    body, params = build_article_put(
        "353023",
        "11",
        resolver,
        {
            "Prosema-Artikelname": "Neuer Name",
            "Farbe": "Grau",
            "Grundmaterial": "TPU",
        },
    )
    assert params == {"ignoreMissingProperties": "true"}
    assert body["version"] == "11"
    assert body["name"] == "Neuer Name"
    assert "id" not in body
    assert "lowLevelCode" not in body
    attrs = body["customAttributes"]
    assert len(attrs) == 2
    ids = {row["attributeDefinitionId"] for row in attrs}
    assert len(ids) == 2
    assert all("stringValue" in row for row in attrs)
    assert {row["stringValue"] for row in attrs} == {"Grau", "TPU"}


def test_native_only_put_omits_custom_attributes_key():
    resolver = CustomAttributeResolver(FakeWeclappClient(_pass1_string_defs()))
    body, _params = build_article_put(
        "353023",
        "7",
        resolver,
        {"Prosema-Langtext": "<p>Hi</p>", "Kurzbeschreibung": "Hi"},
    )
    assert body["longText"] == "<p>Hi</p>"
    assert body["shortDescription1"] == "Hi"
    assert "customAttributes" not in body


def test_ambiguous_label_raises_naming_both_ids():
    defs = _pass1_string_defs() + _defs(
        ("7458", "Im Shop verfügbar (Prosema)"),
        ("7466", "Im Shop verfügbar (Prosema)"),
    )
    resolver = CustomAttributeResolver(FakeWeclappClient(defs))
    with pytest.raises(AmbiguousAttributeLabelError, match="7458") as exc:
        resolver.id_for_label("Im Shop verfügbar (Prosema)")
    assert "7466" in str(exc.value)
    assert "Im Shop verfügbar (Prosema)" in str(exc.value)


def test_resolver_caches_per_instance_and_uses_one_list_call():
    client = FakeWeclappClient(_pass1_string_defs())
    resolver = CustomAttributeResolver(client)
    assert resolver.id_for_label("Farbe") == resolver.id_for_label("Farbe")
    assert client.calls == [("customAttributeDefinition", 1000)]


def test_missing_pass1_label_raises_on_load():
    resolver = CustomAttributeResolver(FakeWeclappClient(_defs(("1", "Farbe"))))
    with pytest.raises(ValueError, match="Grundmaterial"):
        resolver.load()


def test_html_substitution_leaves_tags_byte_identical():
    html = '<p class="lead">Winkelprofil aus Aluminium</p>'
    out = substitute_preserving_markup(html, "Winkelprofil", "WinkelProfil")
    assert out == '<p class="lead">WinkelProfil aus Aluminium</p>'


def test_search_term_inside_attribute_is_not_replaced():
    html = '<a href="/winkelprofil">siehe winkelprofil</a>'
    out = substitute_preserving_markup(html, "winkelprofil", "winkelProfil")
    assert out == '<a href="/winkelprofil">siehe winkelProfil</a>'


def test_plain_text_substitution_unaffected():
    assert (
        substitute_preserving_markup("Winkelprofil Aluminium", "Winkelprofil", "WinkelProfil")
        == "WinkelProfil Aluminium"
    )


def test_malformed_html_does_not_raise_or_lose_content():
    raw = "<div <span>Winkelprofil</span> trailing <"
    out = substitute_preserving_markup(raw, "Winkelprofil", "X")
    assert "X" in out
    assert "trailing <" in out
    assert len(out) == len(raw) - len("Winkelprofil") + len("X")


def test_entity_in_search_is_refused():
    with pytest.raises(ValueError, match="entity"):
        substitute_preserving_markup("a&amp;b", "a&b", "x")
