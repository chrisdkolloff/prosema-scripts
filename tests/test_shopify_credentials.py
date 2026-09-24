"""Per-user Shopify token storage."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.shopify_credentials import (
    NoShopifyToken,
    get_shopify_token_meta,
    load_config_for_user,
    store_shopify_token,
)
from scripts.shopify.config import ShopifyConfig

PLAIN_USER = {"oid": "shopify-user-oid", "name": "Test", "email": "t@example.com", "roles": ["user"]}
SECRET = "shpat_test_secret_token_value"


@pytest.fixture
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


def test_store_and_meta(db_session):
    store_shopify_token(db_session, PLAIN_USER["oid"], SECRET)
    meta = get_shopify_token_meta(db_session, PLAIN_USER["oid"])
    assert meta.stored is True
    assert meta.created_at is not None


def test_load_config_for_user_uses_stored_token(db_session, monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP", "test-shop")
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHOPIFY_CLIENT_SECRET", raising=False)
    store_shopify_token(db_session, PLAIN_USER["oid"], SECRET)
    config = load_config_for_user(db_session, PLAIN_USER["oid"])
    assert isinstance(config, ShopifyConfig)
    assert config.access_token == SECRET
    assert config.shop == "test-shop"


def test_load_config_without_token_or_env_raises(db_session, monkeypatch):
    def _missing_env_config(**_kwargs):
        raise ValueError("Shopify-Zugangsdaten fehlen.")

    monkeypatch.setattr("app.shopify_credentials.load_config", _missing_env_config)
    with pytest.raises(NoShopifyToken):
        load_config_for_user(db_session, "no-token-user")
