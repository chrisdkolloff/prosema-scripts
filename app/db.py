"""Synchronous SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

import logging
from collections.abc import Generator
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


def _sslmode_from_url(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    values = query.get("sslmode")
    if not values:
        return None
    return values[0]


_url_sslmode = _sslmode_from_url(settings.database_url)
_connect_args: dict = {
    "application_name": "prosema-tools",
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
}
if _url_sslmode is None:
    _connect_args["sslmode"] = "require"
    _effective_sslmode = "require"
else:
    _effective_sslmode = _url_sslmode

if _effective_sslmode in ("require", "verify-full"):
    logger.info("database connection sslmode=%s", _effective_sslmode)
else:
    logger.warning("database connection sslmode=%s", _effective_sslmode)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=180,
    pool_size=5,
    max_overflow=5,
    pool_timeout=10,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
