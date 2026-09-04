"""Allowlist and PUT-body builder for article *updates*.

This is not the create path. Do not import, call, or extend
``core.article_payload.row_to_payload``. That function applies CREATE defaults
(empty Aktiv becomes Ja, and others). On an update those defaults would write
values the caller never asked for. Keep the two builders separate.

Attribute definition ids are resolved from a live GET of
``/customAttributeDefinition``, never from ``data/weclapp_article_create_schema.json``.
That file is dated 2026-08-18, lists 26 of 29 current definitions, and contains
two rows labelled "Im Shop verfügbar (Prosema)" (7458 and 7466), so a label
lookup against it is ambiguous by construction.

Nothing in this module sends POST or PUT.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.article_payload import (
    ARTICLE_NAME_FIELD,
    ARTICLE_NUMBER_FIELD,
    LONG_TEXT_FIELD,
)


class Location(str, Enum):
    NATIVE = "NATIVE"
    CUSTOM_ATTR = "CUSTOM_ATTR"


class ValueKind(str, Enum):
    PLAIN_TEXT = "PLAIN_TEXT"
    HTML = "HTML"
    STRING_ATTR = "STRING_ATTR"
    BOOLEAN_ATTR = "BOOLEAN_ATTR"
    LIST_ATTR = "LIST_ATTR"
    NUMERIC = "NUMERIC"


class Writability(str, Enum):
    PASS_1 = "PASS_1"
    LATER = "LATER"
    BLOCKED = "BLOCKED"
    FORBIDDEN = "FORBIDDEN"


class BlockerScope(str, Enum):
    LIVE = "LIVE"
    SNAPSHOT_ONLY = "SNAPSHOT_ONLY"


@dataclass(frozen=True)
class WriteField:
    snapshot_key: str
    target: str
    location: Location
    value_kind: ValueKind
    writability: Writability
    blocker: str | None
    blocker_scope: BlockerScope | None


_LATER_SET = (
    "These need a set-field-to-value operation that does not exist yet, "
    "not a text substitution."
)

_SNAPSHOT_KEYS_INVENTORY: tuple[str, ...] = (
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
    ARTICLE_NAME_FIELD,
    ARTICLE_NUMBER_FIELD,
    LONG_TEXT_FIELD,
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
)


def _f(
    snapshot_key: str,
    target: str,
    location: Location,
    value_kind: ValueKind,
    writability: Writability,
    *,
    blocker: str | None = None,
    blocker_scope: BlockerScope | None = None,
) -> WriteField:
    return WriteField(
        snapshot_key=snapshot_key,
        target=target,
        location=location,
        value_kind=value_kind,
        writability=writability,
        blocker=blocker,
        blocker_scope=blocker_scope,
    )


def _string_attr(snapshot_key: str, *, extra_blocker: str | None = None) -> WriteField:
    return _f(
        snapshot_key,
        snapshot_key,
        Location.CUSTOM_ATTR,
        ValueKind.STRING_ATTR,
        Writability.PASS_1,
        blocker=extra_blocker,
        blocker_scope=BlockerScope.SNAPSHOT_ONLY if extra_blocker else None,
    )


WRITE_FIELDS: tuple[WriteField, ...] = (
    _f(
        ARTICLE_NAME_FIELD,
        "name",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.PASS_1,
    ),
    _f(
        LONG_TEXT_FIELD,
        "longText",
        Location.NATIVE,
        ValueKind.HTML,
        Writability.PASS_1,
        blocker=(
            "Snapshot stores strip_html(plain text); live longText is HTML. "
            "Does not apply when the value comes from a live GET."
        ),
        blocker_scope=BlockerScope.SNAPSHOT_ONLY,
    ),
    _f(
        "Kurzbeschreibung",
        "shortDescription1",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.PASS_1,
    ),
    _f(
        "Referenz (Matchcode)",
        "matchCode",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.PASS_1,
    ),
    _string_attr("Grundmaterial"),
    _string_attr("Oberfläche"),
    _string_attr("Farbe"),
    _string_attr("Produktfamilie"),
    _string_attr("Rabattcode"),
    _string_attr(
        "Verkaufseinheit",
        extra_blocker=(
            "Snapshot flatten rewrites € to CHF. Does not apply when the value "
            "comes from a live GET."
        ),
    ),
    _string_attr("Verpackung"),
    _string_attr("VPE 1"),
    _string_attr("VPE 2"),
    _string_attr("VPE 3"),
    _string_attr("Breite in mm"),
    _string_attr("Höhe in mm"),
    _string_attr("Länge in cm"),
    _string_attr("Gewichtseinheit"),
    _string_attr("Produkt-ID (Prosema)"),
    _string_attr("Varianten-ID (Prosema)"),
    _f(
        ARTICLE_NUMBER_FIELD,
        "articleNumber",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.FORBIDDEN,
        blocker=(
            "Article numbers embed group codes permanently; a bulk rewrite is "
            "unrecoverable."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Hauptgruppe",
        "Hauptwarengruppe (Auswahl)",
        Location.CUSTOM_ATTR,
        ValueKind.LIST_ATTR,
        Writability.FORBIDDEN,
        blocker=(
            "The LIST attribute is a different weclapp object from "
            "articleCategoryId; writing it would set the dropdown while leaving "
            "the real category untouched."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Untergruppe",
        "Warengruppe (Auswahl)",
        Location.CUSTOM_ATTR,
        ValueKind.LIST_ATTR,
        Writability.FORBIDDEN,
        blocker=(
            "The LIST attribute is a different weclapp object from "
            "articleCategoryId; writing it would set the dropdown while leaving "
            "the real category untouched."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Kategorie",
        "articleCategoryId",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.FORBIDDEN,
        blocker="Snapshot holds a Shopify GID, not a category reference.",
        blocker_scope=BlockerScope.SNAPSHOT_ONLY,
    ),
    _f(
        "lowLevelCode",
        "lowLevelCode",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.FORBIDDEN,
        blocker="Read-only; a 400 on this key discards the entire payload.",
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Artikel-ID",
        "id",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.FORBIDDEN,
        blocker="Read-only; a 400 on this key discards the entire payload.",
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Erstellt am",
        "createdDate",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.FORBIDDEN,
        blocker="Read-only; a 400 on this key discards the entire payload.",
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Geändert am",
        "lastModifiedDate",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.FORBIDDEN,
        blocker="Read-only; a 400 on this key discards the entire payload.",
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Aktiv",
        "active",
        Location.NATIVE,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Im Verkauf",
        "availableInSale",
        Location.NATIVE,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Im Shop verfügbar",
        "Im Shop verfügbar (Prosema)",
        Location.CUSTOM_ATTR,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=(
            f"{_LATER_SET} Live tenant has two definitions with this label "
            "(7458 and 7466); label lookup must not pick a favourite."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Im Shop aktiv",
        "Im Shop aktiv (Prosema)",
        Location.CUSTOM_ATTR,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Bestand übertragen",
        "Bestand übertragen (Prosema)",
        Location.CUSTOM_ATTR,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Bodenleger",
        "Bodenleger",
        Location.CUSTOM_ATTR,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=(
            f"{_LATER_SET} Snapshot never stores these booleans (always empty). "
            "Does not apply when the value comes from a live GET."
        ),
        blocker_scope=BlockerScope.SNAPSHOT_ONLY,
    ),
    _f(
        "Dachdecker",
        "Dachdecker",
        Location.CUSTOM_ATTR,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=(
            f"{_LATER_SET} Snapshot never stores these booleans (always empty). "
            "Does not apply when the value comes from a live GET."
        ),
        blocker_scope=BlockerScope.SNAPSHOT_ONLY,
    ),
    _f(
        "Landschaftsgärtner",
        "Landschaftsgärtner",
        Location.CUSTOM_ATTR,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=(
            f"{_LATER_SET} Snapshot never stores these booleans (always empty). "
            "Does not apply when the value comes from a live GET."
        ),
        blocker_scope=BlockerScope.SNAPSHOT_ONLY,
    ),
    _f(
        "Plattenleger",
        "Plattenleger",
        Location.CUSTOM_ATTR,
        ValueKind.BOOLEAN_ATTR,
        Writability.LATER,
        blocker=(
            f"{_LATER_SET} Snapshot never stores these booleans (always empty). "
            "Does not apply when the value comes from a live GET."
        ),
        blocker_scope=BlockerScope.SNAPSHOT_ONLY,
    ),
    _f(
        "Einheit",
        "unitId",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Artikeltyp",
        "articleType",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Steuersatz",
        "taxRateType",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Nettogewicht kg",
        "articleNetWeight",
        Location.NATIVE,
        ValueKind.NUMERIC,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "GTIN (EAN-Nummer)",
        "ean",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.LATER,
        blocker=_LATER_SET,
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Artikelbeschreibung HTML",
        "Artikelbeschreibung (Prosema)",
        Location.CUSTOM_ATTR,
        ValueKind.HTML,
        Writability.BLOCKED,
        blocker=(
            "Live articles keep HTML in native longText; this custom LARGE_TEXT "
            "attribute is empty. Not a substitute for longText."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Einkaufspreis EUR netto",
        "articlePrices",
        Location.NATIVE,
        ValueKind.NUMERIC,
        Writability.BLOCKED,
        blocker=(
            "Snapshot holds a flattened scalar from a supply-source price list. "
            "A PUT needs nested articlePrices / supply-source objects, which "
            "this allowlist does not build."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Verkaufspreis €, BE",
        "articlePrices",
        Location.NATIVE,
        ValueKind.NUMERIC,
        Writability.BLOCKED,
        blocker=(
            "Snapshot holds a flattened GROSS1 scalar. A PUT needs nested "
            "articlePrices objects, which this allowlist does not build."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Lieferantenartikelnummer",
        "articleNumber",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker=(
            "Lives on the primary supply source, not the article. This path "
            "does not PUT articleSupplySource."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Lieferanten Firmenname",
        "company",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker="Party/supplier graph is not on the article PUT.",
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Lieferantennummer",
        "supplierNumber",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker="Party/supplier graph is not on the article PUT.",
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Bezugsquelle-ID",
        "primarySupplySourceId",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker=(
            "Supply-source writes need nested objects this allowlist does not "
            "build."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "Zolltarifnummer",
        "customsTariffNumberId",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker=(
            "Snapshot stores the tariff display name, not customsTariffNumberId."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Breite (m)",
        "articleWidth",
        Location.NATIVE,
        ValueKind.NUMERIC,
        Writability.BLOCKED,
        blocker=(
            "GET-only native in this path; flatten rounds to 3 decimal metres. "
            "Width writes are not in the first-pass allowlist."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Einheit-ID",
        "unitId",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker=(
            "Raw unitId; the named field Einheit is LATER. This extra is not a "
            "transform target."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Kategorie-ID",
        "articleCategoryId",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker=(
            "articleCategoryId is a different object from the shop LIST "
            "dropdowns; category writes are not in this allowlist."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
    _f(
        "weclapp Version",
        "version",
        Location.NATIVE,
        ValueKind.PLAIN_TEXT,
        Writability.BLOCKED,
        blocker=(
            "OCC token is a required argument of the payload builder, not a "
            "transform field. Omitting it is last-write-wins (P4)."
        ),
        blocker_scope=BlockerScope.LIVE,
    ),
)

_BY_KEY: dict[str, WriteField] = {}
for _field in WRITE_FIELDS:
    if _field.snapshot_key in _BY_KEY:
        raise RuntimeError(f"Duplicate write-field key: {_field.snapshot_key}")
    _BY_KEY[_field.snapshot_key] = _field

SNAPSHOT_INVENTORY_KEYS: tuple[str, ...] = _SNAPSHOT_KEYS_INVENTORY


def write_field(snapshot_key: str) -> WriteField:
    field = _BY_KEY.get(snapshot_key)
    if field is None:
        raise KeyError(f"Unknown article write-field key: {snapshot_key!r}")
    return field


def pass_1_fields() -> tuple[WriteField, ...]:
    return tuple(field for field in WRITE_FIELDS if field.writability is Writability.PASS_1)


def pass_1_custom_attr_labels() -> tuple[str, ...]:
    return tuple(
        field.target
        for field in pass_1_fields()
        if field.location is Location.CUSTOM_ATTR
    )


class AmbiguousAttributeLabelError(ValueError):
    """Raised when a custom-attribute label maps to more than one definition id."""


class CustomAttributeResolver:
    """Live definition ids for one job run.

    Keyed by definition id. Label → id is a secondary index. Ambiguous labels
    are recorded and raise when requested; this class never picks a favourite.
    Cache is per instance only.
    """

    def __init__(self, client: Any) -> None:
        self._client = client
        self._by_id: dict[str, dict[str, Any]] | None = None
        self._ids_by_label: dict[str, tuple[str, ...]] = {}

    def load(self) -> None:
        if self._by_id is not None:
            return
        by_id: dict[str, dict[str, Any]] = {}
        ids_by_label: dict[str, list[str]] = {}
        for definition in self._client.iter_pages(
            "customAttributeDefinition",
            page_size=1000,
        ):
            if not isinstance(definition, dict):
                continue
            attr_id = str(definition.get("id") or "").strip()
            label = str(
                definition.get("label") or definition.get("attributeKey") or ""
            ).strip()
            if not attr_id:
                continue
            by_id[attr_id] = definition
            if label:
                ids_by_label.setdefault(label, []).append(attr_id)
        self._by_id = by_id
        self._ids_by_label = {label: tuple(ids) for label, ids in ids_by_label.items()}
        missing = [
            label for label in pass_1_custom_attr_labels() if label not in self._ids_by_label
        ]
        if missing:
            raise ValueError(
                "PASS_1 custom attribute label(s) missing from "
                f"/customAttributeDefinition: {', '.join(missing)}"
            )

    def definition_by_id(self, attr_id: str) -> dict[str, Any]:
        self.load()
        assert self._by_id is not None
        try:
            return self._by_id[attr_id]
        except KeyError as exc:
            raise KeyError(f"Unknown customAttributeDefinition id: {attr_id!r}") from exc

    def id_for_label(self, label: str) -> str:
        self.load()
        ids = self._ids_by_label.get(label)
        if not ids:
            raise ValueError(f"Custom attribute label not found: {label!r}")
        if len(ids) > 1:
            raise AmbiguousAttributeLabelError(
                f"Custom attribute label {label!r} maps to more than one "
                f"definition id: {', '.join(ids)}"
            )
        return ids[0]


_TAG_RE = re.compile(r"(<[^>]*>)")
# Named, decimal, and hex entities. A search/replace that would have to match
# across an entity boundary (for example search "a&b" against text "a&amp;b",
# or search "&" inside "&amp;") cannot be done without decoding, which would
# change bytes we do not own. Those searches are refused.
_ENTITY_RE = re.compile(r"&(?:#[0-9]+|#x[0-9A-Fa-f]+|[a-zA-Z][a-zA-Z0-9]+);")


def _tag_segments(value: str) -> list[str]:
    return _TAG_RE.findall(value)


def assert_markup_tags_unchanged(before: str, after: str) -> None:
    """Self-check: every ``<...>`` segment is byte-identical."""
    if _tag_segments(before) != _tag_segments(after):
        raise RuntimeError(
            "HTML substitution changed markup bytes; refusing to return the result."
        )


def _replace_outside_entities(segment: str, search: str, replacement: str) -> str:
    out: list[str] = []
    pos = 0
    for match in _ENTITY_RE.finditer(segment):
        out.append(segment[pos : match.start()].replace(search, replacement))
        out.append(match.group(0))
        pos = match.end()
    out.append(segment[pos:].replace(search, replacement))
    return "".join(out)


def transform_preserving_markup(value: str, transform: Callable[[str], str]) -> str:
    """Apply ``transform`` to text segments only; tag bytes stay identical."""
    text = "" if value is None else str(value)
    pieces = _TAG_RE.split(text)
    transformed: list[str] = []
    for piece in pieces:
        if piece.startswith("<") and piece.endswith(">") and len(piece) >= 2:
            transformed.append(piece)
        else:
            transformed.append(transform(piece))
    result = "".join(transformed)
    assert_markup_tags_unchanged(text, result)
    return result


def substitute_preserving_markup(value: str, search: str, replacement: str) -> str:
    """Replace ``search`` in text only; bytes inside tags stay identical.

    Split on a tag pattern while keeping delimiters, transform non-tag
    segments, rejoin. Do not parse-and-reserialise (that normalises quotes
    and whitespace).

    If ``search`` contains ``&``, the match would have to interpret or span
    HTML entities. That is refused rather than guessed.
    """
    if "&" in search:
        raise ValueError(
            "Refusing a substitution whose search term contains '&': it would "
            "span or alter an HTML entity boundary."
        )
    text = "" if value is None else str(value)
    if not search:
        assert_markup_tags_unchanged(text, text)
        return text
    return transform_preserving_markup(
        text, lambda segment: _replace_outside_entities(segment, search, replacement)
    )


_PUT_PARAMS: dict[str, str] = {"ignoreMissingProperties": "true"}


def _reject_field(field: WriteField) -> None:
    reason = field.blocker or field.writability.value
    raise ValueError(
        f"Cannot write {field.snapshot_key!r} ({field.writability.value}): {reason}"
    )


def build_article_put(
    article_id: str,
    version: str,
    resolver: CustomAttributeResolver,
    changes: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build a partial article PUT body and its query params.

    ``article_id`` identifies the URL; it is never placed in the body (id is
    read-only and would 400 the whole payload). ``version`` is required so a
    versionless PUT cannot be constructed — weclapp would accept that as
    last-write-wins (P4).
    """
    if article_id is None or str(article_id).strip() == "":
        raise ValueError("article_id is required for PUT /article/id/{id}")
    if version is None or str(version).strip() == "":
        raise ValueError(
            "version is required; omitting it is accepted by weclapp as "
            "last-write-wins"
        )

    body: dict[str, Any] = {"version": str(version)}
    custom_attributes: list[dict[str, str]] = []

    for snapshot_key, new_value in changes.items():
        field = write_field(snapshot_key)
        if field.writability is Writability.FORBIDDEN:
            _reject_field(field)
        if field.writability is not Writability.PASS_1:
            _reject_field(field)
        if field.location is Location.NATIVE:
            body[field.target] = new_value
            continue
        custom_attributes.append(
            {
                "attributeDefinitionId": resolver.id_for_label(field.target),
                "stringValue": new_value,
            }
        )

    if custom_attributes:
        body["customAttributes"] = custom_attributes
    return body, dict(_PUT_PARAMS)
