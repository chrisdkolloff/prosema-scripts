"""Current search choices and compatibility with existing batch rows."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.batch_filter_options import live_filter_options
from app.batches import filtered_rows, row_matches


def row(**values):
    return SimpleNamespace(
        raw_data=values,
        edits={},
        proposed_article_number=None,
        validation_error=None,
        write_error=None,
    )


def test_catalogue_reads_current_values_and_active_suppliers_only():
    client = Mock()
    client.iter_pages.side_effect = [
        [
            {
                "label": "Hauptwarengruppe (Auswahl)",
                "selectableValues": [
                    {"value": "Neu"},
                    {"value": "Alt", "active": False},
                    {"value": "Neu"},
                ],
            }
        ],
        [{"name": "Aktuelle Kategorie"}],
        [
            {"id": "1", "supplierNumber": "100", "company": "Lieferant AG", "supplier": True},
            {
                "id": "2",
                "supplierNumber": "200",
                "company": "Inaktiv",
                "supplier": True,
                "supplierActive": False,
            },
        ],
    ]
    with patch("app.batch_filter_options.weclapp_client_for", return_value=client) as factory:
        result = live_filter_options(Mock(), "current-user")
    assert factory.call_args.args[1] == "current-user"
    assert result["hauptgruppen"] == ["Neu"]
    assert result["kategorien"] == ["Aktuelle Kategorie"]
    assert [s["number"] for s in result["lieferanten"]] == ["100"]
    assert [c.args[0] for c in client.iter_pages.call_args_list] == [
        "customAttributeDefinition",
        "articleCategory",
        "party",
    ]
    client.post.assert_not_called()
    client.put.assert_not_called()


def test_catalogue_does_not_hide_read_failure():
    client = Mock()
    client.iter_pages.side_effect = ValueError("unavailable")
    with (
        patch("app.batch_filter_options.weclapp_client_for", return_value=client),
        pytest.raises(ValueError),
    ):
        live_filter_options(Mock(), "user")


def test_supplier_search_and_filter_match_names_and_numbers():
    item = row(**{"Lieferanten Firmenname": "Lieferant AG", "Lieferantennummer": "100"})
    assert row_matches(item, query="lieferant ag")
    assert row_matches(item, query="100")
    assert row_matches(item, lieferant="100")
    assert not row_matches(item, lieferant="10")
    assert row_matches(item, lieferant="LIEFERANT")
    assert not row_matches(item, lieferant="Andere Firma")
    name_only = row(**{"Lieferanten Firmenname": "Lieferant AG"})
    assert row_matches(name_only, lieferant="100", supplier_names=["Lieferant AG"])


def test_live_group_names_match_historic_coded_batch_labels():
    items = [
        row(Hauptgruppe="Zubehör - 010", Kategorie="Werkzeug"),
        row(Hauptgruppe="Andere - 020", Kategorie="Werkzeug"),
    ]
    matched, total, pages = filtered_rows(items, hauptgruppe="Zubehör", kategorie="Werkzeug")
    assert matched == items[:1]
    assert (total, pages) == (1, 1)
    assert not row_matches(items[0], hauptgruppe="Zubehör - 020")
