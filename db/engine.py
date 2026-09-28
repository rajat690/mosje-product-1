"""SQLAlchemy engine from DATABASE_URL (Postgres via psycopg 3, or SQLite for tests/fallback)."""
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


def normalize_url(url: str) -> str:
    """Render/Heroku style postgres:// or postgresql:// -> postgresql+psycopg:// (psycopg 3)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str | None = None) -> Engine:
    url = normalize_url(url or os.environ.get("DATABASE_URL") or "sqlite:///./mosje_local.db")
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False}, future=True)

        @event.listens_for(eng, "connect")
        def _pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
        return eng
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, future=True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine()


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"
