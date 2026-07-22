"""Node — schema_link.

RAG over hand-curated table cards (pgvector + TEI). On any failure we attach
all cards as a fallback so the pipeline still runs (degraded, not broken).
"""

from __future__ import annotations

from datetime import datetime, timezone

from text2sql_contracts import (
    GraphState,
    NodeName,
    SchemaCard,
    SchemaLinkResult,
)

from app.clients import pgvector_store
from app.observability import get_logger
from app.schema_catalog import ALL_CARDS, card_by_name
from app.settings import get_settings

_log = get_logger(__name__)


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.SCHEMA_LINK)
    started = span.started_at
    s = get_settings()
    used_fallback = False
    cards: list[SchemaCard] = []
    try:
        if not s.schema_link_enabled:
            used_fallback = True
        else:
            await pgvector_store.ensure_index_seeded()
            try:
                rows = await pgvector_store.search(
                    state.request.question, top_k=s.schema_link_top_k
                )
            except Exception as e:  # noqa: BLE001
                _log.warning("schema_link_search_failed", error=str(e))
                rows = []
                used_fallback = True
            for r in rows:
                cards.append(
                    SchemaCard(
                        table=r["table"],
                        description=r["description"],
                        columns=r["columns"],
                        score=r["score"],
                    )
                )

        if not cards:
            used_fallback = True
            cards = [
                SchemaCard(table=c.name, description=c.description,
                           columns=list(c.columns), score=0.0)
                for c in ALL_CARDS
            ]

        state.schema_link = SchemaLinkResult(cards=cards, used_fallback=used_fallback)
        span.attrs["fallback"] = used_fallback
        span.attrs["tables"] = [c.table for c in cards]
        span.attrs["scores"] = [round(c.score, 3) for c in cards]
        _log.info(
            "schema_link_done",
            trace_id=str(state.trace_id),
            fallback=used_fallback,
            tables=[c.table for c in cards],
        )
    finally:
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
    return state


def cards_to_table_cards(cards: list[SchemaCard]) -> list:
    """Convert wire-format SchemaCard -> internal TableCard for prompt rendering."""
    out = []
    for c in cards:
        tc = card_by_name(c.table)
        if tc is not None:
            out.append(tc)
    return out
