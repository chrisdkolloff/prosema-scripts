"""Delegated Microsoft Graph token storage."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.graph_credentials import (
    NoGraphToken,
    get_graph_access_token,
    has_graph_refresh_token,
    store_graph_refresh_token,
)

OID = "graph-test-user"


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


def test_store_and_refresh(db_session):
    store_graph_refresh_token(db_session, OID, "refresh-abc")
    assert has_graph_refresh_token(db_session, OID) is True
    with patch(
        "app.graph_credentials._refresh_access_token",
        return_value="access-xyz",
    ):
        assert get_graph_access_token(db_session, OID) == "access-xyz"


def test_missing_token_raises(db_session):
    with pytest.raises(NoGraphToken):
        get_graph_access_token(db_session, "unknown-oid")
