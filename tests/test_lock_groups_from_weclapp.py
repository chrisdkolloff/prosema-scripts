"""Lock backfill from weclapp article numbers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.groups_service import create_hauptgruppe, create_untergruppe
from app.models import GruppenAudit, Hauptgruppe
from scripts.lock_groups_from_weclapp import (
    apply_locks,
    collect_locks,
    parse_group_codes,
)

ACTOR = {"oid": "test-oid", "name": "Test User"}


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


def _unused_code(db_session, prefix: str = "8") -> str:
    used = {row[0] for row in db_session.execute(select(Hauptgruppe.code)).all()}
    for index in range(100):
        code = f"{prefix}{index:02d}"
        if code not in used:
            return code
    raise RuntimeError("No free test code remaining")


def test_parse_group_codes():
    assert parse_group_codes("020.020.0010") == ("020", "020")
    assert parse_group_codes("060.010.800") == ("060", "010")
    assert parse_group_codes("0010") is None
    assert parse_group_codes("0100.001") is None
    assert parse_group_codes("Standard-Ladehilfsmittel") is None
    assert parse_group_codes("") is None


def test_collect_locks_referenced_groups_and_unresolved(db_session):
    haupt = create_hauptgruppe(
        db_session, code=_unused_code(db_session), name="Lock-Haupt", actor=ACTOR
    )
    other = create_hauptgruppe(
        db_session, code=_unused_code(db_session), name="Unreferenziert", actor=ACTOR
    )
    unter = create_untergruppe(db_session, haupt, code="010", name="Lock-Unter", actor=ACTOR)
    db_session.flush()

    articles = [
        {"id": "1", "articleNumber": f"{haupt.code}.010.0010"},
        {"id": "2", "articleNumber": f"{haupt.code}.010.0020"},
        {"id": "3", "articleNumber": "Standard-Ladehilfsmittel"},
        {"id": "4", "articleNumber": "999.010.0010"},
    ]
    plan = collect_locks(db_session, articles)
    assert plan.articles_processed == 4
    assert list(plan.to_lock_haupt) == [haupt]
    assert plan.to_lock_haupt[haupt] == 2
    assert list(plan.to_lock_unter) == [unter]
    assert other not in plan.to_lock_haupt
    assert len(plan.unresolved) == 2
    assert plan.skipped_haupt == 0

    now = datetime.now(UTC)
    apply_locks(db_session, plan, locked_at=now)
    db_session.flush()
    db_session.refresh(haupt)
    db_session.refresh(unter)
    db_session.refresh(other)
    assert haupt.locked_at is not None
    assert unter.locked_at is not None
    assert other.locked_at is None

    audits = list(
        db_session.scalars(
            select(GruppenAudit).where(
                GruppenAudit.action == "locked_by_backfill",
                GruppenAudit.entity_id.in_([haupt.id, unter.id]),
            )
        )
    )
    assert {row.entity_id for row in audits} == {haupt.id, unter.id}
    assert all(row.actor_oid == "backfill-script" for row in audits)

    again = collect_locks(db_session, articles)
    assert again.to_lock_haupt == {}
    assert again.to_lock_unter == {}
    assert again.skipped_haupt == 1
    assert again.skipped_unter == 1
    apply_locks(db_session, again, locked_at=datetime.now(UTC))
    db_session.flush()
    assert (
        len(
            list(
                db_session.scalars(
                    select(GruppenAudit).where(
                        GruppenAudit.action == "locked_by_backfill",
                        GruppenAudit.entity_id.in_([haupt.id, unter.id]),
                    )
                )
            )
        )
        == 2
    )
