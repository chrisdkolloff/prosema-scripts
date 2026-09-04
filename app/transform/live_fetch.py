"""Load live weclapp articles for transform preview. GET only."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.transform.scope import ScopeCandidate
from scripts.weclapp.client import WeclappClient, WeclappError

ID_IN_CHUNK = 200
PAGE_SIZE = 1000
CATALOGUE_PAGE_THRESHOLD = 1000

_GROUP_PREFIX = re.compile(r"^(\d{3})\.")


@dataclass
class LiveFetchResult:
    articles: dict[str, dict[str, Any]] = field(default_factory=dict)
    gone_ids: set[str] = field(default_factory=set)


def group_prefix(numbers: list[str]) -> str | None:
    """Three-digit Hauptgruppe prefix if every number shares one, else None."""
    prefixes: list[str] = []
    for number in numbers:
        match = _GROUP_PREFIX.match(str(number).strip())
        if match is None:
            return None
        prefixes.append(match.group(1))
    if prefixes and all(item == prefixes[0] for item in prefixes):
        return prefixes[0]
    return None


def _id_in_value(ids: list[str]) -> str:
    return "[" + ",".join(ids) + "]"


def _ingest(wanted: set[str], rows: Any, into: dict[str, dict[str, Any]]) -> set[str]:
    returned: set[str] = set()
    for article in rows or []:
        if not isinstance(article, dict):
            continue
        article_id = str(article.get("id") or "")
        if article_id in wanted:
            into[article_id] = article
            returned.add(article_id)
    return wanted - returned


def fetch_live_articles(
    client: WeclappClient,
    candidates: list[ScopeCandidate],
) -> LiveFetchResult:
    """Load live articles. Ids missing from a successful list page are GONE."""
    wanted = {c.weclapp_id: c for c in candidates if c.weclapp_id}
    result = LiveFetchResult()
    if not wanted:
        return result
    ids = list(wanted)
    numbers = [wanted[i].article_number for i in ids]
    prefix = group_prefix(numbers)
    list_ok = False
    try:
        if prefix is not None and len(ids) > ID_IN_CHUNK:
            missing = _ingest(
                set(wanted),
                client.iter_pages(
                    "article",
                    params={"articleNumber-like": f"{prefix}.%"},
                    page_size=PAGE_SIZE,
                ),
                result.articles,
            )
            result.gone_ids.update(missing)
            list_ok = True
        elif len(ids) > CATALOGUE_PAGE_THRESHOLD:
            missing = _ingest(
                set(wanted),
                client.iter_pages("article", page_size=PAGE_SIZE),
                result.articles,
            )
            result.gone_ids.update(missing)
            list_ok = True
        else:
            for start in range(0, len(ids), ID_IN_CHUNK):
                chunk = ids[start : start + ID_IN_CHUNK]
                missing = _ingest(
                    set(chunk),
                    client.iter_pages(
                        "article",
                        params={"id-in": _id_in_value(chunk)},
                        page_size=PAGE_SIZE,
                    ),
                    result.articles,
                )
                result.gone_ids.update(missing)
            list_ok = True
    except WeclappError as exc:
        if exc.status_code in {401, 403}:
            raise
        list_ok = False

    if list_ok:
        return result

    for article_id in ids:
        if article_id in result.articles or article_id in result.gone_ids:
            continue
        try:
            article = client.get(f"/article/id/{article_id}")
        except WeclappError as exc:
            if exc.status_code == 404:
                result.gone_ids.add(article_id)
                continue
            raise
        if isinstance(article, dict):
            result.articles[article_id] = article
        else:
            result.gone_ids.add(article_id)
    return result
