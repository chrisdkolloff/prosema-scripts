"""Lock group registry rows that are already referenced by weclapp articles.

One-off, run by hand. Not a worker job and not on a schedule. If articles are
created in weclapp outside the week-3 registration tool, re-run this script
manually before week 3 ships.

Group codes are taken from weclapp ``articleNumber`` (Prosema Artikelnummer,
``MMM.SSS.NNNN``). Confirmed against live API output: that field holds the
number; category names and custom attributes are not used.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db import SessionLocal
from app.groups_service import (
    AmbiguousGroupMatch,
    record_audit,
    resolve_hauptgruppe,
    resolve_untergruppe,
    snapshot_hauptgruppe,
    snapshot_untergruppe,
)
from app.models import Hauptgruppe, Untergruppe
from core.numbering import parse_group_codes

BACKFILL_ACTOR = {"oid": "backfill-script", "name": "Lock-Backfill (weclapp)"}


@dataclass
class UnresolvedArticle:
    article_id: str
    article_number: str
    raw_value: str
    reason: str

    def format(self) -> str:
        return (
            f"id={self.article_id} number={self.article_number!r} "
            f"value={self.raw_value!r} ({self.reason})"
        )


@dataclass
class LockPlan:
    articles_processed: int = 0
    to_lock_haupt: dict[object, int] = field(default_factory=dict)
    to_lock_unter: dict[object, int] = field(default_factory=dict)
    skipped_haupt: int = 0
    skipped_unter: int = 0
    unresolved: list[UnresolvedArticle] = field(default_factory=list)


def _article_id(article: dict[str, Any]) -> str:
    return str(article.get("id") or "")


def _article_number(article: dict[str, Any]) -> str:
    return str(article.get("articleNumber") or "")


def collect_locks(db: Session, articles: Iterable[dict[str, Any]]) -> LockPlan:
    """Resolve articles to groups. Does not write."""
    plan = LockPlan()
    haupt_cache: dict[str, Hauptgruppe | None] = {}
    unter_cache: dict[tuple[str, str], Untergruppe | None] = {}
    haupt_hits: dict[object, int] = defaultdict(int)
    unter_hits: dict[object, int] = defaultdict(int)

    for article in articles:
        plan.articles_processed += 1
        article_id = _article_id(article)
        number = _article_number(article)
        codes = parse_group_codes(number)
        if codes is None:
            plan.unresolved.append(
                UnresolvedArticle(
                    article_id=article_id,
                    article_number=number,
                    raw_value=number,
                    reason="Artikelnummer hat nicht die Form MMM.SSS.NNNN",
                )
            )
            continue
        main_code, sub_code = codes
        try:
            if main_code not in haupt_cache:
                haupt_cache[main_code] = resolve_hauptgruppe(db, main_code)
            haupt = haupt_cache[main_code]
            if haupt is None:
                plan.unresolved.append(
                    UnresolvedArticle(
                        article_id=article_id,
                        article_number=number,
                        raw_value=main_code,
                        reason="Hauptgruppe nicht im Register",
                    )
                )
                continue
            unter_key = (main_code, sub_code)
            if unter_key not in unter_cache:
                unter_cache[unter_key] = resolve_untergruppe(db, haupt, sub_code)
            unter = unter_cache[unter_key]
            if unter is None:
                plan.unresolved.append(
                    UnresolvedArticle(
                        article_id=article_id,
                        article_number=number,
                        raw_value=f"{main_code}.{sub_code}",
                        reason="Untergruppe nicht im Register",
                    )
                )
                continue
        except AmbiguousGroupMatch as exc:
            plan.unresolved.append(
                UnresolvedArticle(
                    article_id=article_id,
                    article_number=number,
                    raw_value=number,
                    reason=str(exc),
                )
            )
            continue
        haupt_hits[haupt] += 1
        unter_hits[unter] += 1

    for group, count in haupt_hits.items():
        if group.locked_at is not None:
            plan.skipped_haupt += 1
        else:
            plan.to_lock_haupt[group] = count
    for group, count in unter_hits.items():
        if group.locked_at is not None:
            plan.skipped_unter += 1
        else:
            plan.to_lock_unter[group] = count
    return plan


def apply_locks(db: Session, plan: LockPlan, *, locked_at: datetime) -> None:
    """Set locked_at and write audit rows. Caller commits."""
    locked_iso = locked_at.isoformat()
    for group, count in plan.to_lock_haupt.items():
        before = snapshot_hauptgruppe(group)
        group.locked_at = locked_at
        record_audit(
            db,
            entity="hauptgruppe",
            entity_id=group.id,
            action="locked_by_backfill",
            actor=BACKFILL_ACTOR,
            before=before,
            after={
                "locked_at": locked_iso,
                "source": "weclapp article count",
                "article_count": count,
            },
        )
    for group, count in plan.to_lock_unter.items():
        before = snapshot_untergruppe(group)
        group.locked_at = locked_at
        record_audit(
            db,
            entity="untergruppe",
            entity_id=group.id,
            action="locked_by_backfill",
            actor=BACKFILL_ACTOR,
            before=before,
            after={
                "locked_at": locked_iso,
                "source": "weclapp article count",
                "article_count": count,
            },
        )
    db.flush()


def format_report(plan: LockPlan, *, committed: bool) -> str:
    lines = [
        f"Artikel verarbeitet: {plan.articles_processed}",
        f"Hauptgruppen neu gesperrt: {len(plan.to_lock_haupt)}",
        f"Untergruppen neu gesperrt: {len(plan.to_lock_unter)}",
        f"Hauptgruppen bereits gesperrt (übersprungen): {plan.skipped_haupt}",
        f"Untergruppen bereits gesperrt (übersprungen): {plan.skipped_unter}",
        f"Artikel nicht aufgelöst: {len(plan.unresolved)}",
    ]
    if plan.to_lock_haupt or plan.to_lock_unter:
        lines.append("Würde sperren:" if not committed else "Gesperrt:")
        for group in sorted(plan.to_lock_haupt, key=lambda item: item.code):
            lines.append(
                f"  Hauptgruppe {group.code} {group.name} "
                f"({plan.to_lock_haupt[group]} Artikel)"
            )
        for group in sorted(
            plan.to_lock_unter,
            key=lambda item: (item.hauptgruppe.code, item.code),
        ):
            lines.append(
                f"  Untergruppe {group.hauptgruppe.code}.{group.code} {group.name} "
                f"({plan.to_lock_unter[group]} Artikel)"
            )
    if plan.unresolved:
        lines.append("Nicht aufgelöst:")
        lines.extend(f"  {item.format()}" for item in plan.unresolved)
    if not committed:
        lines.append("Dry-run: nichts geschrieben. Zum Schreiben --commit übergeben.")
    return "\n".join(lines)


def iter_weclapp_articles() -> Iterable[dict[str, Any]]:
    from scripts.weclapp.client import WeclappClient
    from scripts.weclapp.config import load_config

    client = WeclappClient(load_config())
    return client.iter_pages("article", params={"properties": "id,articleNumber"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gruppen im Register sperren, die bereits von weclapp-Artikeln "
            "referenziert werden. Einmaliges Hand-Skript, kein Auftrag und kein "
            "Zeitplan. Werden Artikel direkt in weclapp angelegt (ausserhalb des "
            "Artikelregistrierungs-Tools), dieses Skript vor Week 3 erneut "
            "von Hand ausführen."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prüfen und Zusammenfassung drucken, ohne zu schreiben (Standard)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="locked_at in der Datenbank setzen",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        plan = collect_locks(db, iter_weclapp_articles())
        if args.commit:
            apply_locks(db, plan, locked_at=datetime.now(UTC))
            db.commit()
            print(format_report(plan, committed=True))
        else:
            db.rollback()
            print(format_report(plan, committed=False))
        return 1 if plan.unresolved else 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
