"""Node — opa_check.

Runs *after* sql_validate so we have a trustworthy table list. We only check
SELECT in Phase 2 (sql_validate already refuses the rest), but the policy is
written to support more ops later without code changes here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from text2sql_contracts import GraphState, NodeError, NodeName, OpaDecision
from text2sql_contracts.errors import ErrorCode

from app.clients.opa_client import evaluate
from app.observability import get_logger

_log = get_logger(__name__)


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.OPA_CHECK)
    started = span.started_at
    try:
        if state.sql_validated is None or not state.sql_validated.safe:
            span.status = "skipped"
            return state
        payload = {
            "user": {
                "id": state.request.user.id,
                "role": state.request.user.role.value,
                "business_unit": state.request.user.business_unit,
            },
            "tables": state.sql_validated.tables_used,
            "ops": ["SELECT"],
        }
        raw = await evaluate(payload)
        obligations = raw.get("obligations", {})
        if not isinstance(obligations, dict):
            obligations = {}
        decision = OpaDecision(
            allow=bool(raw.get("allow", False)),
            reasons=list(raw.get("reasons", [])),
            matched_policy=raw.get("matched_policy"),
            obligations=obligations,
        )
        state.opa = decision
        span.attrs["allow"] = decision.allow
        span.attrs["reasons"] = decision.reasons
        span.attrs["matched_policy"] = decision.matched_policy
        if not decision.allow:
            span.status = "error"
            state.errors.append(
                NodeError(
                    node=NodeName.OPA_CHECK.value,
                    code=ErrorCode.OPA_DENIED,
                    message=("opa_denied: " + "; ".join(decision.reasons)) or "opa_denied",
                    details={"reasons": decision.reasons,
                             "matched_policy": decision.matched_policy},
                )
            )
        _log.info(
            "opa_check_done",
            trace_id=str(state.trace_id),
            allow=decision.allow,
            reasons=decision.reasons,
        )
    finally:
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
    return state
