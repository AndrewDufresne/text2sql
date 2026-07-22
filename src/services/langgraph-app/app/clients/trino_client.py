"""Trino client (sync `trino` driver wrapped via `asyncio.to_thread`).

Phase 1: passes `X-Trino-User` from the request user (identity passthrough §C11).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import trino
from trino.exceptions import TrinoUserError

from app.settings import get_settings


def _execute_sync(
    *, sql: str, user_id: str, trace_id: str, role: str, app_version: str
) -> tuple[list[str], list[list[Any]], int]:
    s = get_settings()
    conn = trino.dbapi.connect(
        host=s.trino_host,
        port=s.trino_port,
        user=user_id,
        catalog=s.trino_catalog,
        schema=s.trino_schema,
        source=s.trino_source,
        client_tags=[f"app=text2sql", f"role={role}", f"version={app_version}"],
        extra_credential=[],
        http_headers={"X-Trino-Trace-Token": trace_id},
    )
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        return columns, [list(r) for r in rows], len(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def execute_sql(
    *, sql: str, user_id: str, trace_id: str, role: str, app_version: str
) -> tuple[list[str], list[list[Any]], int, int]:
    """Returns (columns, rows, row_count, elapsed_ms)."""
    started = time.perf_counter()
    cols, rows, n = await asyncio.to_thread(
        _execute_sync,
        sql=sql,
        user_id=user_id,
        trace_id=trace_id,
        role=role,
        app_version=app_version,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return cols, rows, n, elapsed_ms


__all__ = ["execute_sql", "TrinoUserError"]
