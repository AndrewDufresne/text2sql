"""pgvector store for schema cards.

Single table `schema_card(table_name, description, columns_csv, embedding)`.
Created in `config/postgres-cib/init/02_seed_account_exposure.sql`. We:

  - upsert all hand-written cards at app start (idempotent, embeds via TEI)
  - search top-K cosine-nearest for a question

Connection is a tiny asyncpg pool; we keep it inside this module so the rest
of the codebase stays free of asyncpg specifics.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg

from app.clients.tei_client import embed
from app.observability import get_logger
from app.schema_catalog import ALL_CARDS, TableCard
from app.settings import get_settings

_log = get_logger(__name__)
_pool: asyncpg.Pool | None = None
_init_lock = asyncio.Lock()
_initialized: bool = False


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(s.pgv_dsn, min_size=1, max_size=4)
    return _pool


def _vec_literal(values: list[float]) -> str:
    """pgvector text format: '[v1,v2,...]'."""
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


async def ensure_index_seeded() -> None:
    """Idempotent: embed and upsert all cards if not present yet."""
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return
        try:
            pool = await _get_pool()
            texts = [c.card_text for c in ALL_CARDS]
            embs = await embed(texts)
            async with pool.acquire() as cx:
                for card, vec in zip(ALL_CARDS, embs, strict=True):
                    await cx.execute(
                        """
                        INSERT INTO schema_card (table_name, description, columns_csv, embedding)
                        VALUES ($1, $2, $3, $4::vector)
                        ON CONFLICT (table_name) DO UPDATE
                          SET description = EXCLUDED.description,
                              columns_csv = EXCLUDED.columns_csv,
                              embedding   = EXCLUDED.embedding
                        """,
                        card.name,
                        card.description,
                        ",".join(card.columns),
                        _vec_literal(vec),
                    )
            _initialized = True
            _log.info("schema_index_seeded", count=len(ALL_CARDS))
        except Exception as e:  # noqa: BLE001
            _log.warning("schema_index_seed_failed", error=str(e))


async def search(question: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Return [{table, description, columns, score}, ...] sorted by similarity.

    Embeds the question via TEI, then runs cosine-distance search against the
    pre-seeded schema_card table. The vector literal is inlined into the SQL
    rather than passed as a parameter because asyncpg's ``$1::vector`` cast
    does not handle the ``<=>`` operator correctly (returns 0 rows even when
    the table has matching embeddings — verified 2026-07-22). All values are
    floats from TEI's response so there is no SQL-injection risk.
    """
    pool = await _get_pool()
    embs = await embed([question])
    qvec = _vec_literal(embs[0])
    async with pool.acquire() as cx:
        rows = await cx.fetch(
            f"""
            SELECT table_name, description, columns_csv,
                   1 - (embedding <=> '{qvec}'::vector) AS score
            FROM schema_card
            ORDER BY score DESC
            LIMIT {int(top_k)}
            """
        )
    _log.debug("schema_search_done", top_k=top_k, rows_found=len(rows))
    return [
        dict(
            table=r["table_name"],
            description=r["description"],
            columns=r["columns_csv"].split(","),
            score=float(r["score"]),
        )
        for r in rows
    ]


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# Helper exposed for tests.
def reset_for_tests() -> None:
    global _pool, _initialized
    _pool = None
    _initialized = False


def card_from_row(row: dict[str, Any]) -> TableCard:
    return TableCard(
        name=row["table"],
        description=row["description"],
        columns=tuple(row["columns"]),
    )
