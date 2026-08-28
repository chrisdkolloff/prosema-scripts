"""General-purpose audit_log writes. Caller owns the transaction."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit_log(
    db: Session,
    *,
    actor: Mapping[str, Any],
    entity_type: str,
    entity_id: str | uuid.UUID,
    action: str,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_oid=str(actor["oid"]),
        actor_name=str(actor.get("name") or actor["oid"]),
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        detail=detail,
    )
    db.add(row)
    return row
