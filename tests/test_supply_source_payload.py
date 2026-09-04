"""Payload builder: the nine live weclapp facts as unit tests."""

from __future__ import annotations

import pytest

from app.supply_source_payload import (
    PUT_PARAMS,
    SupplySourcePayloadError,
    build_article_attach_put,
    build_supply_source_post,
    build_supply_source_put,
)

LIVE_GET = {
    "id": "353019",
    "version": "4",
    "articlePrices": [
        {"id": "353344", "price": "48.9", "version": "0", "createdDate": 1},
        {"id": "353020", "price": "48.22", "endDate": 1787608799000},
    ],
}


def test_version_required_cannot_omit():
    with pytest.raises(TypeError):
        build_supply_source_put(supply_source_id="1")  # type: ignore[call-arg]
    with pytest.raises(SupplySourcePayloadError, match="version is required"):
        build_supply_source_put(supply_source_id="1", version="")
    with pytest.raises(SupplySourcePayloadError, match="version is required"):
        build_supply_source_put(supply_source_id="1", version=None)  # type: ignore[arg-type]


def test_ignore_missing_properties_on_every_put():
    body, params = build_supply_source_put(supply_source_id="1", version="2", name="x")
    assert params == PUT_PARAMS
    assert params["ignoreMissingProperties"] == "true"
    assert "createdDate" not in body


def test_unknown_property_article_id_rejected():
    from app.supply_source_payload import _reject_forbidden

    with pytest.raises(SupplySourcePayloadError, match="articleId"):
        _reject_forbidden({"id": "1", "version": "1", "name": "x", "articleId": "9"})


def test_last_modified_user_rejected():
    from app.supply_source_payload import _reject_forbidden

    with pytest.raises(SupplySourcePayloadError, match="lastModifiedByUserId"):
        _reject_forbidden({"id": "1", "version": "1", "lastModifiedByUserId": "x"})


def test_empty_article_prices_raises():
    with pytest.raises(SupplySourcePayloadError, match="articlePrices: \\[\\]"):
        build_supply_source_put(
            supply_source_id="1",
            version="1",
            article_prices=[],
            live_get=LIVE_GET,
        )


def test_omit_article_prices_leaves_key_out():
    body, _ = build_supply_source_put(supply_source_id="1", version="1", name="n")
    assert "articlePrices" not in body


def test_article_prices_require_live_get():
    with pytest.raises(SupplySourcePayloadError, match="live GET"):
        build_supply_source_put(
            supply_source_id="1",
            version="1",
            article_prices=[{"price": "1"}],
        )


def test_nested_price_id_only_from_this_get():
    body, _ = build_supply_source_put(
        supply_source_id="1",
        version="1",
        article_prices=[
            {"id": "353344", "price": "1", "createdDate": 99, "version": "0"},
            {"id": "DEAD-ID", "price": "2"},
        ],
        live_get=LIVE_GET,
    )
    ids = [row.get("id") for row in body["articlePrices"]]
    assert "353344" in ids
    assert "DEAD-ID" not in ids
    assert "createdDate" not in body["articlePrices"][0]
    assert "version" not in body["articlePrices"][0]


def test_strips_reduction_addition_ids():
    body, _ = build_supply_source_put(
        supply_source_id="1",
        version="1",
        article_prices=[
            {
                "id": "353344",
                "price": "1",
                "reductionAdditions": [
                    {"id": "r1", "version": "0", "type": "REDUCTION_PERCENT", "value": "50"}
                ],
            }
        ],
        live_get=LIVE_GET,
    )
    adds = body["articlePrices"][0]["reductionAdditions"]
    assert "id" not in adds[0]
    assert "version" not in adds[0]
    assert adds[0]["value"] == "50"


def test_create_is_minimal_b3_and_rejects_article_id_in_allowlist():
    body = build_supply_source_post(
        supplier_id="4406",
        article_number="SAN",
        name="Name",
        unit_id="3566",
    )
    assert set(body) == {"supplierId", "articleNumber", "name", "unitId"}


def test_currency_id_is_not_validated_against_party():
    body, _ = build_supply_source_put(
        supply_source_id="1",
        version="1",
        article_prices=[{"id": "353344", "price": "1", "currencyId": "not-a-party-currency"}],
        live_get=LIVE_GET,
    )
    assert body["articlePrices"][0]["currencyId"] == "not-a-party-currency"


def test_article_attach_sends_sources_and_primary_together():
    body, params = build_article_attach_put(
        article_id="353023",
        version="21",
        supply_sources=[
            {
                "id": "nested",
                "articleSupplySourceId": "353019",
                "createdDate": 1,
                "positionNumber": 1,
            }
        ],
        primary_supply_source_id="353019",
    )
    assert params == PUT_PARAMS
    assert body["primarySupplySourceId"] == "353019"
    assert body["supplySources"] == [
        {"articleSupplySourceId": "353019", "positionNumber": 1}
    ]
    assert "createdDate" not in body["supplySources"][0]
