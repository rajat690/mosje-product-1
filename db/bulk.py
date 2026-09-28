"""Fast bulk insert: COPY on PostgreSQL (psycopg 3), executemany elsewhere (SQLite)."""
from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection


def bulk_insert(conn: Connection, table: str, cols: Sequence[str], rows: Iterable[Sequence], chunk: int = 5000) -> int:
    n = 0
    if conn.dialect.name == "postgresql":
        raw = conn.connection.driver_connection          # psycopg.Connection (same transaction)
        with raw.cursor() as cur:
            with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
                    n += 1
        return n
    stmt = text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
    buf = []
    for r in rows:
        buf.append(dict(zip(cols, r)))
        if len(buf) >= chunk:
            conn.execute(stmt, buf)
            n += len(buf)
            buf = []
    if buf:
        conn.execute(stmt, buf)
        n += len(buf)
    return n
