"""Regression for stale selectable-value IDs and current uncoded group labels."""

import copy

import pytest

from app.batch_group_options import GroupOptions
from scripts.weclapp.article_import import _load_schema

MAIN = "Hauptwarengruppe (Auswahl)"
SUB = "Warengruppe (Auswahl)"
VALUES = {"Hauptgruppe": "Zubehör - 010", "Untergruppe": "Werkzeug - 030"}


def definitions(main="Zubehör", sub="Werkzeug"):
    return [
        {
            "id": "new-main-field",
            "label": MAIN,
            "attributeType": "LIST",
            "selectableValues": [{"id": "new-main", "value": main}],
        },
        {
            "id": "new-sub-field",
            "label": SUB,
            "attributeType": "LIST",
            "selectableValues": [{"id": "new-sub", "value": sub}],
        },
    ]


@pytest.mark.parametrize(
    "main,sub",
    [
        ("Zubehör", "Werkzeug"),
        ("Zubehör - 010", "Werkzeug - 30"),
        ("zubehör - 10", "WERKZEUG - 030"),
    ],
)
def test_refresh_old_approved_payload_uses_current_ids_without_changing_content(main, sub):
    payload = {
        "articleNumber": "999.999.0010",
        "name": "Freigegebener Artikel",
        "customAttributes": [
            {"attributeDefinitionId": "226369", "selectedValueId": "226370"},
            {"attributeDefinitionId": "226383", "selectedValueId": "226386"},
            {"attributeDefinitionId": "other", "stringValue": "Unverändert"},
        ],
    }
    before = copy.deepcopy(payload)
    options = GroupOptions(definitions(main, sub), _load_schema())
    refreshed = options.refresh(payload, VALUES)
    assert payload == before
    assert refreshed == {
        **before,
        "customAttributes": [
            {"attributeDefinitionId": "other", "stringValue": "Unverändert"},
            {"attributeDefinitionId": "new-main-field", "selectedValueId": "new-main"},
            {"attributeDefinitionId": "new-sub-field", "selectedValueId": "new-sub"},
        ],
    }


@pytest.mark.parametrize("sub", ["Werkzeuge", "Werkzeug - 040", ""])
def test_missing_or_conflicting_group_aborts_instead_of_reusing_old_id(sub):
    with pytest.raises(ValueError, match="Gruppenverwaltung"):
        GroupOptions(definitions(sub=sub), _load_schema()).refresh({}, VALUES)


def test_ambiguous_name_is_rejected():
    defs = definitions()
    defs[1]["selectableValues"].append({"id": "another", "value": "Werkzeug - 30"})
    with pytest.raises(ValueError, match="mehrdeutig"):
        GroupOptions(defs, _load_schema()).refresh({}, VALUES)


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"readOnly": True},
        {"attributeType": "TEXT"},
        {"selectableValues": None},
        {"id": ""},
    ],
)
def test_unwritable_definition_is_rejected(change):
    defs = definitions()
    defs[0].update(change)
    with pytest.raises(ValueError, match="nicht beschreibbar"):
        GroupOptions(defs, _load_schema())


def test_empty_or_duplicate_definition_catalogue_is_rejected():
    for defs in ([], [*definitions(), definitions()[0]]):
        with pytest.raises(ValueError, match="nicht eindeutig"):
            GroupOptions(defs, _load_schema())


def test_missing_registry_value_is_rejected():
    with pytest.raises(ValueError, match="Gruppenzuordnung fehlt"):
        GroupOptions(definitions(), _load_schema()).refresh({}, {})


@pytest.mark.parametrize("defs", [[None], ["not a definition"]])
def test_malformed_catalogue_is_rejected(defs):
    with pytest.raises(ValueError, match="ungültig"):
        GroupOptions(defs, _load_schema())


def test_malformed_option_is_rejected():
    defs = definitions()
    defs[0]["selectableValues"] = [None]
    with pytest.raises(ValueError, match="ungültig"):
        GroupOptions(defs, _load_schema())
