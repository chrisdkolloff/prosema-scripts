"""weclapp unit catalogue for the supply-source grid.

Live probe 2026-09-04 on supply source 353019 (article 999.999.001 only):
PUT ``unitId`` 3566 → 4259 with ignoreMissingProperties returned 400
``unit cannot be changed``. The article ``unitId`` stayed 3566. Version did not
bump. Changing unit on an existing supply source is not writable.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import WeclappArticle, WeclappUnit

# See module docstring. Do not send unitId on PUT of an existing supply source.
UNIT_ID_PUT_WRITABLE = False

UNIT_LOCKED_HINT = (
    "Einheit einer bestehenden Bezugsquelle. weclapp lässt sie nach dem Anlegen "
    "nicht mehr ändern."
)


def units_for_dropdown(db: Session) -> list[dict[str, str]]:
    """All catalogue units, usage-desc so unused names fall to the bottom."""
    counts = dict(
        db.execute(
            select(WeclappArticle.unit_id, func.count())
            .where(WeclappArticle.unit_id.is_not(None))
            .where(WeclappArticle.missing_since.is_(None))
            .group_by(WeclappArticle.unit_id)
        ).all()
    )
    rows = list(db.scalars(select(WeclappUnit)).all())
    rows.sort(
        key=lambda u: (-int(counts.get(u.weclapp_id) or 0), (u.name or "").casefold())
    )
    return [
        {
            "id": u.weclapp_id,
            "name": u.name,
            "description": u.description or "",
        }
        for u in rows
    ]
