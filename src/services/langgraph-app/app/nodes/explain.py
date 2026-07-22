"""Node — explain (Phase 3).

After a successful execute, generate a 1-2 sentence NL explanation of what
the SQL did and what the user is looking at.  We deliberately:

  * NEVER block on failure (network/LLM errors flag `failed=True`, the graph
    still returns OK with the SQL + rows).
  * Pass only column names + first few rows (sanitized) to the LLM, so we
    don't re-leak unmasked rows out to LiteLLM.  Output of this node is
    re-masked by `output_mask` before it reaches the user.
  * Use a separate generation_name in LiteLLM so cost / latency is broken
    out per-step in Langfuse.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from text2sql_contracts import (
    ExplanationResult,
    GraphState,
    NodeError,
    NodeName,
)
from text2sql_contracts.errors import ErrorCode

from app.clients.litellm import generate_explanation
from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)

PROMPT_VERSION = "explain@v1"

_SYSTEM = """\
You are a careful banking analyst assistant.

Given a user's question, the SQL that was executed, and a small preview of
the result, produce ONE short paragraph (max 3 sentences) describing what
the answer means in plain business English.  Do NOT restate the SQL.  Do
NOT invent numbers; only refer to what's in the preview. If the preview
is empty, say so plainly.
"""


def _make_user_prompt(state: GraphState) -> str:
    cols = state.execution.columns if state.execution else []
    rows = (state.execution.rows[:5] if state.execution else [])
    preview_lines = [", ".join(str(c) for c in row) for row in rows]
    preview = "\n".join(preview_lines) or "(no rows)"
    return (
        f"Question: {state.request.question}\n\n"
        f"SQL:\n{state.sql_validated.sql if state.sql_validated else '(unknown)'}\n\n"
        f"Result columns: {', '.join(cols)}\n"
        f"First rows:\n{preview}\n"
    )


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.EXPLAIN)
    started = span.started_at
    s = get_settings()
    if not s.explain_enabled or state.execution is None:
        state.explanation = ExplanationResult(
            text="", model=None, prompt_version=PROMPT_VERSION, failed=False
        )
        span.status = "skipped"
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
        return state
    text = ""
    model: str | None = None
    failed = False
    try:
        text, meta = await generate_explanation(
            system_prompt=_SYSTEM,
            user_prompt=_make_user_prompt(state),
            trace_id=str(state.trace_id),
            user_id=state.request.user.id,
            session_id=state.request.session_id,
        )
        model = meta.get("model")
        span.attrs["model"] = model
        span.attrs["prompt_tokens"] = meta.get("prompt_tokens", 0)
        span.attrs["completion_tokens"] = meta.get("completion_tokens", 0)
        span.attrs["chars"] = len(text)
        span.status = "ok"
        _log.info("explain_ok", trace_id=str(state.trace_id), chars=len(text))
    except Exception as e:  # noqa: BLE001
        failed = True
        span.status = "error"
        state.errors.append(
            NodeError(
                node=NodeName.EXPLAIN.value,
                code=ErrorCode.EXPLAIN_FAILED,
                message=str(e),
            )
        )
        _log.warning("explain_failed", trace_id=str(state.trace_id), error=str(e))
    finally:
        ended = datetime.now(timezone.utc)
        span.ended_at = ended
        span.elapsed_ms = int((ended - started).total_seconds() * 1000)
    state.explanation = ExplanationResult(
        text=text or "",
        model=model,
        prompt_version=PROMPT_VERSION,
        elapsed_ms=span.elapsed_ms,
        failed=failed,
    )
    return state
