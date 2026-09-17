"""Retired article numbers must keep high-water marks (no reissue of vacated tip)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow, RetiredArticleNumber
from app.numbering_high_water import seed_high_water


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


def test_retired_number_blocks_reissue_of_high_water_tip(db_session):
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant="t",
        row_count=1,
        columns=[],
        created_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()
    db_session.add(
        ArticleSnapshotRow(
            snapshot_id=snap.id,
            position=0,
            data={"Prosema Artikelnummer": "999.999.0030"},
            article_number="999.999.0030",
            article_name="Tip",
            active=True,
            weclapp_id="1",
        )
    )
    db_session.add(
        RetiredArticleNumber(
            weclapp_article_id="2",
            retired_number="999.999.0030",
            new_number="999.999.0040",
            destination_haupt="999",
            destination_unter="999",
            created_by_oid="oid",
            created_by_name="Tester",
        )
    )
    db_session.flush()
    counters = seed_high_water(db_session)
    assert counters.get(("999", "999")) == 30
