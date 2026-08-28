"""High-water and weclapp list-label matching for article registration."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow
from app.numbering_high_water import seed_high_water
from scripts.weclapp.article_import import LookupTables, _load_schema


def test_high_water_includes_inactive_snapshot_rows():
    connection = engine.connect()
    trans = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        snap = ArticleSnapshot(
            status="complete",
            created_by_oid="t",
            created_by_name="t",
            weclapp_tenant="test",
            row_count=2,
            columns=[],
        )
        db.add(snap)
        db.flush()
        db.add(
            ArticleSnapshotRow(
                snapshot_id=snap.id,
                position=0,
                data={},
                article_number="999.999.0500",
                article_name="inactive high",
                active=False,
            )
        )
        db.add(
            ArticleSnapshotRow(
                snapshot_id=snap.id,
                position=1,
                data={},
                article_number="999.999.0020",
                article_name="active low",
                active=True,
            )
        )
        db.flush()
        counters = seed_high_water(db)
        assert counters[("999", "999")] == 500
    finally:
        db.close()
        trans.rollback()
        connection.close()


def test_list_value_id_matches_integer_code_despite_padding():
    lookups = LookupTables(_load_schema())
    # Registry-style 3-digit padding vs weclapp's 2-digit Warengruppe label.
    option_id = lookups.list_value_id("Warengruppe (Auswahl)", "Nivelliersystem - 010")
    literal = lookups.list_value_literal("Warengruppe (Auswahl)", "Nivelliersystem - 010")
    assert literal == "Nivelliersystem - 10"
    assert option_id == lookups.list_value_id("Warengruppe (Auswahl)", "Nivelliersystem - 10")


def test_list_value_id_hauptgruppe_padded_codes_still_match():
    lookups = LookupTables(_load_schema())
    a = lookups.list_value_id("Hauptwarengruppe (Auswahl)", "Zubehör - 010")
    b = lookups.list_value_id("Hauptwarengruppe (Auswahl)", "Zubehör - 10")
    # Hauptwarengruppe uses 3-digit codes in weclapp; integer 10 == 010.
    assert a == b
    assert lookups.list_value_literal("Hauptwarengruppe (Auswahl)", "Zubehör - 10") == "Zubehör - 010"
