"""Node 1 — sql_generate (Phase 2).

Differences from Phase 1:
  - Schema description comes from `state.schema_link.cards` (RAG output),
    falling back to the full catalog when the linker decided to fall back.
  - On a re-attempt (`state.repair_attempts > 0`) we add a `User reminder`
    section listing the violations from the previous validate pass — this
    is the simplest possible self-repair signal that does not require a
    second LLM round-trip from the validator.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from text2sql_contracts import GraphState, NodeError, NodeName
from text2sql_contracts.errors import ErrorCode

from app.clients.litellm import generate_sql
from app.nodes.schema_link import cards_to_table_cards
from app.observability import get_logger
from app.schema_catalog import render_prompt_schema

_log = get_logger(__name__)

PROMPT_VERSION = "sql_generate@v1"

_SYSTEM_RULES = """\
You are a careful SQL assistant for a corporate banking analytics platform.

Rules - violation will cause your output to be rejected:
1. Output ONLY a single SQL SELECT statement. No prose, no comments, no markdown fences.
2. Read-only: no INSERT/UPDATE/DELETE/DDL/CALL/SET/USE/MERGE/COPY/EXPLAIN.
3. Reference ONLY the table(s) listed below.
4. Always include an explicit LIMIT (default 1000).
5. Use ANSI SQL accepted by Trino. Quote identifiers with double quotes only when needed.
"""


def build_system_prompt(state: GraphState) -> str:
    cards = cards_to_table_cards(state.schema_link.cards) if state.schema_link else None
    schema_block = render_prompt_schema(cards)
    repair_hint = ""
    if state.repair_attempts > 0 and state.sql_validated is not None:
        violations = "; ".join(state.sql_validated.violations) or "unknown"
        repair_hint = (
            f"\n\nUser reminder (your previous answer was rejected): "
            f"{violations}. Please regenerate strictly following all rules.\n"
        )
    return f"{_SYSTEM_RULES}\n{schema_block}{repair_hint}"


_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _strip_fences(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip().rstrip(";").strip()


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.SQL_GENERATE)
    started = span.started_at
    try:
        system_prompt = build_system_prompt(state)
        text, meta = await generate_sql(
            system_prompt=system_prompt,
            user_prompt=state.request.question,
            trace_id=str(state.trace_id),
            user_id=state.request.user.id,
            session_id=state.request.session_id,
        )
        sql = _strip_fences(text)
        state.sql_draft = sql
        span.attrs["model"] = meta.get("model")
        span.attrs["prompt_version"] = PROMPT_VERSION
        span.attrs["prompt_tokens"] = meta.get("prompt_tokens", 0)
        span.attrs["completion_tokens"] = meta.get("completion_tokens", 0)
        span.attrs["repair_attempt"] = state.repair_attempts
        span.attrs["sql_preview"] = sql[:200]
        span.status = "ok"
        _log.info(
            "sql_generate_ok",
            trace_id=str(state.trace_id),
            sql_chars=len(sql),
            repair_attempt=state.repair_attempts,
        )
    except Exception as e:  # noqa: BLE001
        span.status = "error"
        state.errors.append(
            NodeError(
                node=NodeName.SQL_GENERATE.value,
                code=ErrorCode.LLM_FAILED,
                message=str(e),
            )
        )
        _log.error("sql_generate_failed", trace_id=str(state.trace_id), error=str(e))
    finally:
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
    return state
