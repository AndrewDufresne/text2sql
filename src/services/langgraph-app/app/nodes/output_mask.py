"""Node — output_mask (Phase 3).

Run AFTER `execute` (and `explain`).  We re-run Presidio (or the offline
fallback) on every string cell of the result set and on the NL explanation,
replacing detected PII spans in-place with `<ENTITY_TYPE>`.

Design notes:
  * Non-blocking. If Presidio is down we degrade to the offline regex
    detector, same as `pii_guard`. We never refuse on output: by the time we
    get here we already authorized + executed; suppressing the answer would
    be a worse failure mode than leaking a single masked-by-fallback row.
  * Idempotent. Mask result is recorded in `state.output_mask` so the trace
    shows what was redacted (counts only, never raw values).
  * Same `_PII_BLOCK_TYPES` allow-list as `pii_guard` keeps "industry" /
    "USD" / country names from being mangled.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from text2sql_contracts import (
    ExecutionResult,
    GraphState,
    NodeError,
    NodeName,
    OutputMaskResult,
)
from text2sql_contracts.errors import ErrorCode

from app.clients.presidio_client import analyze, anonymize
from app.nodes.pii_guard import _PII_BLOCK_TYPES
from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)


def _filter_block_types(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [h for h in hits if h.get("entity_type") in _PII_BLOCK_TYPES]


async def _mask_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    if not text:
        return text, []
    hits = _filter_block_types(await analyze(text))
    if not hits:
        return text, []
    return await anonymize(text, hits), hits


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.OUTPUT_MASK)
    started = span.started_at
    s = get_settings()
    counts: dict[str, int] = {}
    cells_scanned = 0
    cells_masked = 0
    explanation_masked = False
    enabled = s.pii_enabled and s.output_mask_enabled
    state.output_mask = OutputMaskResult(enabled=enabled)
    try:
        if not enabled:
            span.status = "skipped"
            return state
        if state.execution is not None:
            cols = state.execution.columns
            new_rows: list[list[Any]] = []
            for row in state.execution.rows:
                new_row: list[Any] = []
                for cell in row:
                    if isinstance(cell, str) and cell.strip():
                        cells_scanned += 1
                        masked, hits = await _mask_text(cell)
                        if hits:
                            cells_masked += 1
                            for h in hits:
                                et = str(h.get("entity_type", "UNKNOWN"))
                                counts[et] = counts.get(et, 0) + 1
                        new_row.append(masked)
                    else:
                        new_row.append(cell)
                new_rows.append(new_row)
            state.execution = ExecutionResult(
                columns=cols,
                rows=new_rows,
                row_count=state.execution.row_count,
                truncated=state.execution.truncated,
                elapsed_ms=state.execution.elapsed_ms,
            )
        if state.explanation is not None and state.explanation.text:
            masked, hits = await _mask_text(state.explanation.text)
            if hits:
                explanation_masked = True
                for h in hits:
                    et = str(h.get("entity_type", "UNKNOWN"))
                    counts[et] = counts.get(et, 0) + 1
                state.explanation.text = masked
        state.output_mask = OutputMaskResult(
            enabled=True,
            cells_scanned=cells_scanned,
            cells_masked=cells_masked,
            explanation_masked=explanation_masked,
            entity_counts=counts,
        )
        span.attrs["cells_scanned"] = cells_scanned
        span.attrs["cells_masked"] = cells_masked
        span.attrs["entity_counts"] = counts
        span.status = "ok"
        _log.info(
            "output_mask_done",
            trace_id=str(state.trace_id),
            cells_masked=cells_masked,
            cells_scanned=cells_scanned,
        )
    except Exception as e:  # noqa: BLE001
        span.status = "error"
        # Non-blocking: record the error but don't fail the request.
        state.errors.append(
            NodeError(
                node=NodeName.OUTPUT_MASK.value,
                code=ErrorCode.OUTPUT_MASK_FAILED,
                message=str(e),
            )
        )
        _log.warning("output_mask_failed", trace_id=str(state.trace_id), error=str(e))
    finally:
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
    return state
