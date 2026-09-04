"""Tests for the weclapp supply-source index build (read-only)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.jobs import HANDLERS
from app.models import (
    Supplier,
    SupplierArticleAlias,
    WeclappArticle,
    WeclappSupplySource,
    WeclappSupplySourceLink,
)
from app.supply_source_index import (
    DuplicateSupplySourceError,
    find_duplicate_supply_sources,
    pull_supply_source_index,
)


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


def test_duplicate_precheck_groups_by_party_and_san():
    rows = [
        {"id": "1", "supplierId": "4406", "articleNumber": "AAA"},
        {"id": "2", "supplierId": "4406", "articleNumber": "AAA"},
        {"id": "3", "supplierId": "4406", "articleNumber": "BBB"},
    ]
    dups = find_duplicate_supply_sources(rows)
    assert dups == [("4406", "AAA", ["1", "2"])]


class _FakeClient:
    PAGE_SIZE = 1000

    def __init__(self, *, articles, supply_sources, parties, currencies=None, attrs=None):
        self.articles = articles
        self.supply_sources = supply_sources
        self.parties = parties
        self.currencies = currencies or [{"id": "261", "name": "EUR"}]
        self.attrs = attrs or [{"id": "1", "label": "Rabattcode"}]

    def get(self, path, *, params=None):
        if path.startswith("/party/id/"):
            pid = path.rsplit("/", 1)[-1]
            return self.parties[pid]
        if path == "/article":
            return {"result": self.articles}
        if path == "/articleSupplySource":
            return {"result": self.supply_sources}
        if path == "/currency":
            return {"result": self.currencies}
        if path == "/customAttributeDefinition":
            return {"result": self.attrs}
        raise AssertionError(path)


def _client_two_articles_one_ss():
    ss = {
        "id": "162262",
        "version": "1",
        "supplierId": "4406",
        "articleNumber": "95000630CI31",
        "name": "shared",
        "articlePrices": [{"id": "p1", "price": "1.00", "currencyId": "261"}],
    }
    articles = [
        {
            "id": "a1",
            "version": "1",
            "articleNumber": "060.030.0040",
            "name": "one",
            "primarySupplySourceId": "162262",
            "supplySources": [{"articleSupplySourceId": "162262", "positionNumber": 1}],
            "customAttributes": [],
        },
        {
            "id": "a2",
            "version": "1",
            "articleNumber": "060.030.0070",
            "name": "two",
            "primarySupplySourceId": "162262",
            "supplySources": [{"articleSupplySourceId": "162262", "positionNumber": 1}],
            "customAttributes": [],
        },
    ]
    return _FakeClient(
        articles=articles,
        supply_sources=[ss],
        parties={"4406": {"supplierNumber": "10000"}},
    )


def test_index_build_shared_ss_two_links(db_session):
    result = pull_supply_source_index(
        db_session,
        oid="unused",
        client=_client_two_articles_one_ss(),
    )
    assert result["supply_source_count"] == 1
    assert result["link_count"] == 2
    assert result["duplicate_groups"] == 0
    links = list(db_session.scalars(select(WeclappSupplySourceLink)))
    assert {row.article_number for row in links} == {"060.030.0040", "060.030.0070"}
    aliases = list(db_session.scalars(select(SupplierArticleAlias)))
    sans = {(a.supplier_article_number, a.article_number) for a in aliases}
    assert ("95000630CI31", "060.030.0040") in sans
    assert ("95000630CI31", "060.030.0070") in sans


def test_duplicate_ss_fails_before_insert(db_session):
    client = _FakeClient(
        articles=[],
        supply_sources=[
            {"id": "1", "supplierId": "4406", "articleNumber": "X", "version": "1"},
            {"id": "2", "supplierId": "4406", "articleNumber": "X", "version": "1"},
        ],
        parties={"4406": {"supplierNumber": "10000"}},
    )
    with pytest.raises(DuplicateSupplySourceError, match="Lieferant 10000"):
        pull_supply_source_index(db_session, oid="unused", client=client)
    assert db_session.scalar(select(WeclappSupplySource).limit(1)) is None


def test_filtered_pull_does_not_mark_other_supplier_missing(db_session):
    other = WeclappSupplySource(
        weclapp_id="other-ss",
        supplier_party_id="197093",
        supplier_number="10061",
        supplier_article_number="LENZ-1",
        weclapp_version="1",
        last_seen_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC
        ),
        missing_since=None,
    )
    db_session.add(other)
    db_session.flush()

    dural = db_session.scalars(
        select(Supplier).where(Supplier.supplier_number == "10000")
    ).one()
    client = _FakeClient(
        articles=[
            {
                "id": "a1",
                "version": "1",
                "articleNumber": "010.010.0010",
                "primarySupplySourceId": "ss-dural",
                "supplySources": [{"articleSupplySourceId": "ss-dural"}],
                "customAttributes": [],
            }
        ],
        supply_sources=[
            {
                "id": "ss-dural",
                "version": "1",
                "supplierId": "4406",
                "articleNumber": "D1",
                "articlePrices": [],
            }
        ],
        parties={"4406": {"supplierNumber": "10000"}},
    )
    pull_supply_source_index(
        db_session, oid="unused", supplier_id=dural.id, client=client
    )
    db_session.expire_all()
    leftover = db_session.get(WeclappSupplySource, "other-ss")
    assert leftover is not None
    assert leftover.missing_since is None


def test_index_job_registered():
    assert "weclapp_supply_source_index" in HANDLERS


def test_articles_table_exists_after_pull(db_session):
    pull_supply_source_index(
        db_session, oid="u", client=_client_two_articles_one_ss()
    )
    assert db_session.get(WeclappArticle, "a1") is not None
