"""Chat thread + message persistence (server-side history).

Uses a tiny asyncpg pool against postgres-platform (the same Postgres that
already hosts Langfuse and Cube). Tables are created on first use; safe to
import on cold start because the pool is lazy.

The schema is intentionally narrow — no joins, no soft-deletes, no auth —
so it can be inlined in v1 without a migration tool. M7 will move this to
Alembic + role-based access.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.observability import get_logger

_log = get_logger(__name__)

# Default points at postgres-platform (Langfuse / Cube share this DB).
_DSN_DEFAULT = (
    "postgresql://t2sql:t2sql_dev_only@postgres-platform:5432/t2sql_platform"
)
_DSN = os.environ.get("CHAT_STORE_DSN", _DSN_DEFAULT)

_pool: asyncpg.Pool | None = None
_init_lock = asyncio.Lock()
_initialized: bool = False

_DDL = """
CREATE TABLE IF NOT EXISTS chat_thread (
    id          uuid PRIMARY KEY,
    user_id     varchar(120) NOT NULL,
    title       varchar(240) NOT NULL,
    created_at  timestamptz  NOT NULL DEFAULT now(),
    updated_at  timestamptz  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chat_thread_user_updated
    ON chat_thread (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_message (
    id           bigserial PRIMARY KEY,
    thread_id    uuid        NOT NULL REFERENCES chat_thread(id) ON DELETE CASCADE,
    role         varchar(16) NOT NULL,        -- 'user' | 'assistant' | 'system'
    content      text        NOT NULL,
    query_id     uuid,                        -- == QueryResponse.trace_id when role='assistant'
    payload      jsonb,                       -- full QueryResponse for replay/render
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chat_message_thread_created
    ON chat_message (thread_id, created_at);
"""


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    return _pool


async def _ensure_schema() -> None:
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return
        pool = await _get_pool()
        async with pool.acquire() as cx:
            await cx.execute(_DDL)
        _initialized = True
        _log.info("chat_store_schema_ready")


# ---------------------------------------------------------------- threads ----
async def create_thread(user_id: str, title: str) -> dict[str, Any]:
    await _ensure_schema()
    pool = await _get_pool()
    tid = uuid4()
    async with pool.acquire() as cx:
        row = await cx.fetchrow(
            """
            INSERT INTO chat_thread (id, user_id, title)
            VALUES ($1, $2, $3)
            RETURNING id, user_id, title, created_at, updated_at
            """,
            tid,
            user_id,
            title[:240] or "Untitled",
        )
    return _row_to_thread(row)


async def list_threads(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    await _ensure_schema()
    pool = await _get_pool()
    async with pool.acquire() as cx:
        rows = await cx.fetch(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM chat_thread
            WHERE user_id = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    return [_row_to_thread(r) for r in rows]


async def get_thread(thread_id: UUID, user_id: str) -> dict[str, Any] | None:
    await _ensure_schema()
    pool = await _get_pool()
    async with pool.acquire() as cx:
        row = await cx.fetchrow(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM chat_thread
            WHERE id = $1 AND user_id = $2
            """,
            thread_id,
            user_id,
        )
    return _row_to_thread(row) if row else None


async def rename_thread(thread_id: UUID, user_id: str, title: str) -> bool:
    await _ensure_schema()
    pool = await _get_pool()
    async with pool.acquire() as cx:
        result = await cx.execute(
            """
            UPDATE chat_thread SET title = $3, updated_at = now()
            WHERE id = $1 AND user_id = $2
            """,
            thread_id,
            user_id,
            title[:240] or "Untitled",
        )
    return result.endswith(" 1")


async def delete_thread(thread_id: UUID, user_id: str) -> bool:
    await _ensure_schema()
    pool = await _get_pool()
    async with pool.acquire() as cx:
        result = await cx.execute(
            "DELETE FROM chat_thread WHERE id = $1 AND user_id = $2",
            thread_id,
            user_id,
        )
    return result.endswith(" 1")


# --------------------------------------------------------------- messages ----
async def append_message(
    thread_id: UUID,
    role: str,
    content: str,
    query_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await _ensure_schema()
    pool = await _get_pool()
    async with pool.acquire() as cx:
        async with cx.transaction():
            row = await cx.fetchrow(
                """
                INSERT INTO chat_message (thread_id, role, content, query_id, payload)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                RETURNING id, thread_id, role, content, query_id, payload, created_at
                """,
                thread_id,
                role,
                content,
                query_id,
                _jsonb(payload),
            )
            await cx.execute(
                "UPDATE chat_thread SET updated_at = now() WHERE id = $1",
                thread_id,
            )
    return _row_to_message(row)


async def list_messages(
    thread_id: UUID, user_id: str, limit: int = 200
) -> list[dict[str, Any]] | None:
    """Returns None when the thread does not exist for this user."""
    await _ensure_schema()
    pool = await _get_pool()
    async with pool.acquire() as cx:
        owns = await cx.fetchval(
            "SELECT 1 FROM chat_thread WHERE id = $1 AND user_id = $2",
            thread_id,
            user_id,
        )
        if not owns:
            return None
        rows = await cx.fetch(
            """
            SELECT id, thread_id, role, content, query_id, payload, created_at
            FROM chat_message
            WHERE thread_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            thread_id,
            limit,
        )
    return [_row_to_message(r) for r in rows]


# ----------------------------------------------------------------- close -----
async def close() -> None:
    global _pool, _initialized
    if _pool is not None:
        await _pool.close()
    _pool = None
    _initialized = False


# ----------------------------------------------------------------- utils -----
def _jsonb(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    import json

    return json.dumps(payload, default=str)


def _row_to_thread(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "user_id": row["user_id"],
        "title": row["title"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _row_to_message(row: Any) -> dict[str, Any]:
    import json

    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "id": int(row["id"]),
        "thread_id": str(row["thread_id"]),
        "role": row["role"],
        "content": row["content"],
        "query_id": str(row["query_id"]) if row["query_id"] else None,
        "payload": payload,
        "created_at": row["created_at"].isoformat(),
    }
