"""Apply db/migrations/*.sql in order (idempotent). Usage: python -m db.migrate"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .engine import get_engine

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
log = logging.getLogger("mosje.migrate")


def _statements(sql: str):
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    for stmt in "\n".join(lines).split(";"):
        if stmt.strip():
            yield stmt.strip()


def migrate(engine: Engine | None = None) -> list[str]:
    engine = engine or get_engine()
    applied_now = []
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations "
                          "(filename TEXT PRIMARY KEY, applied_at TIMESTAMP)"))
        done = {r[0] for r in conn.execute(text("SELECT filename FROM schema_migrations"))}
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        with engine.begin() as conn:
            for stmt in _statements(f.read_text(encoding="utf-8")):
                conn.execute(text(stmt))
            conn.execute(text("INSERT INTO schema_migrations (filename, applied_at) VALUES (:f, :t)"),
                         {"f": f.name, "t": datetime.now(timezone.utc)})
        applied_now.append(f.name)
        log.info("applied migration %s", f.name)
    return applied_now


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("applied:", migrate() or "nothing (up to date)")
