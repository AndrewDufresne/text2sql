"""Node 3 — execute against Trino with the user's identity (no impersonation)."""

from __future__ import annotations

from datetime import datetime, timezone

from text2sql_contracts import ExecutionResult, GraphState, NodeError, NodeName
from text2sql_contracts.errors import ErrorCode

from app.clients.trino_client import execute_sql
from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.EXECUTE)
    started = span.started_at
    s = get_settings()
    try:
        if state.sql_validated is None or not state.sql_validated.safe:
            span.status = "skipped"
            return state
        cols, rows, n, elapsed = await execute_sql(
            sql=state.sql_validated.sql,
            user_id=state.request.user.id,
            trace_id=str(state.trace_id),
            role=state.request.user.role.value,
            app_version=s.app_version,
        )
        truncated = n >= state.request.preferences.row_limit
        state.execution = ExecutionResult(
            columns=cols, rows=rows, row_count=n, truncated=truncated, elapsed_ms=elapsed
        )
        span.attrs["row_count"] = n
        span.attrs["elapsed_ms"] = elapsed
        span.status = "ok"
        _log.info("execute_ok", trace_id=str(state.trace_id), row_count=n, elapsed_ms=elapsed)
    except Exception as e:  # noqa: BLE001
        span.status = "error"
        state.errors.append(
            NodeError(
                node=NodeName.EXECUTE.value,
                code=ErrorCode.SQL_EXECUTION_FAILED,
                message=str(e),
            )
        )
        _log.error("execute_failed", trace_id=str(state.trace_id), error=str(e))
    finally:
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
    return state
