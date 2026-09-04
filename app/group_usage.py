"""Reject group deletes while articles still use the group."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.assistant.catalog import snapshot_for_query
from app.groups_service import GroupRegistryError
from app.models import ArticleSnapshotRow, Hauptgruppe, Untergruppe
from scripts.weclapp.client import WeclappClient, WeclappError

MSG_NO_SNAPSHOT = (
    "Diese Gruppe kann nicht gelöscht werden: Es sind bereits Artikelnummern "
    "darunter vergeben, aber keine aktuelle Artikelübersicht zum Prüfen. "
    "Bitte zuerst eine Artikelübersicht abfragen und die Artikel umhängen."
)


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


def _snapshot_article_count(
    db: Session, *, number_prefix: str, group_name: str, kind: str
) -> int | None:
    snapshot = snapshot_for_query(db)
    if snapshot is None:
        return None
    prefix = f"{number_prefix}."
    name_match = (
        ArticleSnapshotRow.hauptgruppe_code == group_name
        if kind == "hauptgruppe"
        else ArticleSnapshotRow.untergruppe_code == group_name
    )
    count = db.scalar(
        select(func.count())
        .select_from(ArticleSnapshotRow)
        .where(
            ArticleSnapshotRow.snapshot_id == snapshot.id,
            or_(
                ArticleSnapshotRow.article_number.startswith(prefix),
                name_match,
            ),
        )
    )
    return int(count or 0)


def refuse_delete_if_articles_remain(
    db: Session,
    *,
    number_prefix: str,
    locked: bool,
    kind: str,
    group_name: str,
    weclapp_count: int | None = None,
) -> None:
    if weclapp_count is not None:
        _refuse(weclapp_count, number_prefix=number_prefix, kind=kind)
        return
    snapshot_count = _snapshot_article_count(
        db, number_prefix=number_prefix, group_name=group_name, kind=kind
    )
    if snapshot_count is None:
        if locked:
            raise GroupRegistryError(MSG_NO_SNAPSHOT)
        return
    _refuse(snapshot_count, number_prefix=number_prefix, kind=kind)


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
        locked=group.locked_at is not None,
        kind="untergruppe",
        group_name=group.name,
        weclapp_count=_weclapp_unter_count(client, group),
    )


def refuse_hauptgruppe_delete(
    db: Session, group: Hauptgruppe, *, client: WeclappClient | None = None
) -> None:
    refuse_delete_if_articles_remain(
        db,
        number_prefix=group.code,
        locked=group.locked_at is not None,
        kind="hauptgruppe",
        group_name=group.name,
        weclapp_count=_weclapp_haupt_count(client, group),
    )
