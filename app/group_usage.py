"""Reject group deletes while articles still use the group."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.groups_service import GroupRegistryError
from app.models import Hauptgruppe, Untergruppe
from app.snapshot_groups import count_snapshot_category_assignment
from scripts.weclapp.client import WeclappClient, WeclappError


def noah_reassign_prompt(number_prefix: str) -> str:
    return (
        f"Ordne alle Artikel, deren Artikelnummer mit {number_prefix} anfangen, "
        "der Haupt- und Untergruppe XXX.YYY zu."
    )


def _refuse(count: int, *, number_prefix: str, kind: str) -> None:
    n = int(count)
    if n <= 0:
        return
    verb = "ist" if n == 1 else "sind"
    label = "Hauptgruppe" if kind == "hauptgruppe" else "Untergruppe"
    raise GroupRegistryError(
        (
            f"Diese {label} kann nicht gelöscht werden: Noch {n} Artikel "
            f"{verb} dieser Gruppe zugeordnet. Bitte die Artikel zuerst einer "
            "anderen Gruppe zuordnen, sonst bleiben Nummern und Kategorie uneinheitlich."
        ),
        prompt=noah_reassign_prompt(number_prefix),
    )


def refuse_delete_if_articles_remain(
    db: Session,
    *,
    number_prefix: str,
    haupt_code: str,
    unter_code: str = "",
    kind: str,
    weclapp_count: int | None = None,
) -> None:
    """Block delete when articles are still in this weclapp category (not number prefix)."""
    snapshot_count = count_snapshot_category_assignment(
        db, haupt_code=haupt_code, unter_code=unter_code
    )
    if snapshot_count is not None:
        _refuse(snapshot_count, number_prefix=number_prefix, kind=kind)
        return
    if weclapp_count is not None:
        _refuse(weclapp_count, number_prefix=number_prefix, kind=kind)


def _weclapp_unter_count(client: WeclappClient | None, group: Untergruppe) -> int | None:
    if client is None:
        return None
    from app.weclapp_categories import count_articles_in_unter_category

    parent = group.hauptgruppe
    try:
        return count_articles_in_unter_category(
            client,
            parent_name=parent.name,
            parent_code=parent.code,
            unter_name=group.name,
            unter_code=group.code,
        )
    except WeclappError:
        return None


def _weclapp_haupt_count(client: WeclappClient | None, group: Hauptgruppe) -> int | None:
    if client is None:
        return None
    from app.weclapp_categories import count_articles_in_haupt_category

    try:
        return count_articles_in_haupt_category(
            client, haupt_name=group.name, haupt_code=group.code
        )
    except WeclappError:
        return None


def refuse_untergruppe_delete(
    db: Session, group: Untergruppe, *, client: WeclappClient | None = None
) -> None:
    parent = group.hauptgruppe
    refuse_delete_if_articles_remain(
        db,
        number_prefix=f"{parent.code}.{group.code}",
        haupt_code=parent.code,
        unter_code=group.code,
        kind="untergruppe",
        weclapp_count=_weclapp_unter_count(client, group),
    )


def refuse_hauptgruppe_delete(
    db: Session, group: Hauptgruppe, *, client: WeclappClient | None = None
) -> None:
    refuse_delete_if_articles_remain(
        db,
        number_prefix=group.code,
        haupt_code=group.code,
        kind="hauptgruppe",
        weclapp_count=_weclapp_haupt_count(client, group),
    )
