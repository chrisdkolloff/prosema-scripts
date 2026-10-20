"""Submit regression with an isolated DB double and mocked weclapp responses."""

import copy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.batch_submit import LicenceAbort, run_batch_submit
from scripts.weclapp.client import WeclappError


def _setup():
    batch = SimpleNamespace(id="batch", status="approved")
    row = SimpleNamespace(
        id="row",
        position=1,
        include=True,
        weclapp_article_id=None,
        raw_data={"Hauptgruppe": "Zubehör - 010", "Untergruppe": "Werkzeug - 030"},
        edits={},
        proposed_article_number="999.999.0010",
        write_error="old error",
        approved_payload={
            "articleNumber": "999.999.0010",
            "name": "Approved",
            "unitId": "3566",
            "articleType": "STORABLE",
            "taxRateType": "STANDARD",
            "customAttributes": [
                {"attributeDefinitionId": "226369", "selectedValueId": "226370"},
                {"attributeDefinitionId": "226383", "selectedValueId": "226386"},
            ],
        },
    )
    db = MagicMock()
    db.scalars.return_value.first.return_value = batch
    db.get.side_effect = lambda model, key: row if key == "row" else batch
    client = MagicMock()
    client.iter_pages.return_value = [
        {
            "id": "226369",
            "label": "Hauptwarengruppe (Auswahl)",
            "attributeType": "LIST",
            "selectableValues": [{"id": "current-main", "value": "Zubehör"}],
        },
        {
            "id": "226383",
            "label": "Warengruppe (Auswahl)",
            "attributeType": "LIST",
            "selectableValues": [{"id": "current-sub", "value": "Werkzeug"}],
        },
    ]
    client.get.return_value = {"result": []}
    client.post.return_value = {"id": "created"}
    return db, batch, row, client


def _run(db, row, client):
    with (
        patch("app.batch_submit.weclapp_client_for", return_value=client),
        patch("app.batch_submit._pending_rows", return_value=[row]),
        patch("app.batch_submit._all_included", return_value=[row]),
        patch("app.batch_submit._lock_groups_if_needed"),
        patch("app.batch_submit.record_audit_log") as audit,
    ):
        result = run_batch_submit(db, batch_id="batch", actor_oid="test-user")
    return result, audit


def test_existing_approved_batch_posts_current_ids_and_preserves_approval():
    db, batch, row, client = _setup()
    approved = copy.deepcopy(row.approved_payload)
    result, audit = _run(db, row, client)
    sent = client.post.call_args.kwargs["json"]
    assert [a["selectedValueId"] for a in sent["customAttributes"]] == [
        "current-main",
        "current-sub",
    ]
    assert row.approved_payload == approved
    assert batch.status == "submitted"
    assert result["succeeded"] == 1
    client.iter_pages.assert_called_once_with("customAttributeDefinition")
    assert audit.call_args_list[0].kwargs["detail"]["customAttributes"] == sent["customAttributes"]


@pytest.mark.parametrize("status", [403, 400])
def test_catalogue_failure_writes_nothing_and_keeps_batch_retryable(status):
    db, batch, row, client = _setup()
    client.iter_pages.side_effect = WeclappError("catalogue unavailable", status_code=status)
    expected = LicenceAbort if status == 403 else ValueError
    with pytest.raises(expected):
        _run(db, row, client)
    client.post.assert_not_called()
    assert batch.status == "approved"
    assert row.weclapp_article_id is None


def test_missing_option_fails_before_first_post():
    db, batch, row, client = _setup()
    client.iter_pages.return_value[1]["selectableValues"] = []
    with pytest.raises(ValueError, match="Gruppenverwaltung"):
        _run(db, row, client)
    client.post.assert_not_called()
    assert batch.status == "approved"


def test_retry_fetches_new_ids_again():
    db, batch, row, client = _setup()
    client.post.side_effect = WeclappError("rejected", status_code=400)
    with pytest.raises(ValueError, match="0 von 1"):
        _run(db, row, client)
    assert batch.status == "approved"
    client.post.side_effect = None
    client.iter_pages.return_value[0]["selectableValues"][0]["id"] = "replacement-main"
    _run(db, row, client)
    assert client.iter_pages.call_count == 2
    assert (
        client.post.call_args.kwargs["json"]["customAttributes"][0]["selectedValueId"]
        == "replacement-main"
    )


def test_all_rows_are_checked_before_any_post():
    db, batch, first, client = _setup()
    second = copy.deepcopy(first)
    second.id = "row-2"
    second.position = 2
    second.raw_data["Untergruppe"] = "Fehlende Untergruppe - 040"
    with (
        patch("app.batch_submit.weclapp_client_for", return_value=client),
        patch("app.batch_submit._pending_rows", return_value=[first, second]),
        pytest.raises(ValueError, match="Fehlende Untergruppe"),
    ):
        run_batch_submit(db, batch_id="batch", actor_oid="test-user")
    client.post.assert_not_called()
    assert batch.status == "approved"
