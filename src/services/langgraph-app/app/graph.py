"""Phase 2 graph runner.

Pipeline (linear with one conditional self-repair edge):

    pii_guard
      ├── refused -> END (REFUSED)
      └── ok
           v
    schema_link
           v
    sql_generate
           v
    sql_validate
      ├── safe ----> opa_check
      └── unsafe -> [retry?] -> sql_generate (max SELF_REPAIR_MAX times)
                    [no]    -> END (REFUSED, SQL_UNSAFE)

    opa_check
      ├── allow -> execute -> END (OK)
      └── deny  -> END (REFUSED, OPA_DENIED)

We deliberately keep this as a hand-written async function rather than
`langgraph.StateGraph` for now: 5 nodes + 1 loop is still tractable and
keeps the dependency surface (and image size) small. ADR-0004 marks this
as a Phase 3 conversion.
"""

from __future__ import annotations

import time

from text2sql_contracts import (
    ErrorPayload,
    GraphState,
    QueryRequest,
    QueryResponse,
    QueryStatus,
    ResultPayload,
)
from text2sql_contracts.errors import ErrorCode

from app.clients.langfuse_client import emit_trace
from app.metrics import (
    LATENCY_SECONDS,
    REQUESTS_TOTAL,
    SECURITY_BLOCKS_TOTAL,
    SELF_REPAIR_TOTAL,
)
from app.nodes import execute as node_execute
from app.nodes import explain as node_explain
from app.nodes import opa_check as node_opa
from app.nodes import output_mask as node_output_mask
from app.nodes import pii_guard as node_pii
from app.nodes import schema_link as node_schema
from app.nodes import sql_generate as node_sql_generate
from app.nodes import sql_validate as node_sql_validate
from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)


async def run_query(req: QueryRequest) -> QueryResponse:
    started = time.perf_counter()
    s = get_settings()
    state = GraphState(trace_id=req.trace_id, request=req)

    # 1. PII / injection guard
    #    - Prompt injection → refuse immediately (security bar stays at 100%).
    #    - PII detected  → sanitize (Presidio anonymize) and continue;
    #      the sanitized text replaces the original question in the state.
    state = await node_pii.run(state)
    if state.pii is not None and state.pii.injection_suspected:
        return _to_failure(state, started, status=QueryStatus.REFUSED,
                           code=ErrorCode.PROMPT_INJECTION)

    # 2. Schema-link (RAG)
    state = await node_schema.run(state)

    # 3. Generate -> validate, with optional self-repair loop
    state = await node_sql_generate.run(state)
    if state.errors and state.sql_draft is None:
        return _to_failure(state, started, status=QueryStatus.ERROR,
                           code=ErrorCode.LLM_FAILED)

    state = await node_sql_validate.run(state)
    while (
        state.sql_validated is not None
        and not state.sql_validated.safe
        and state.repair_attempts < s.self_repair_max
    ):
        state.repair_attempts += 1
        SELF_REPAIR_TOTAL.inc()
        # Drop the old NodeError so the retry doesn't leak old failure into
        # the final response, but keep the rejected sql_validated for the
        # repair-hint prompt.
        state.errors = [e for e in state.errors if e.node != "sql_validate"]
        state = await node_sql_generate.run(state)
        if state.errors and state.sql_draft is None:
            return _to_failure(state, started, status=QueryStatus.ERROR,
                               code=ErrorCode.LLM_FAILED)
        state = await node_sql_validate.run(state)

    if state.sql_validated is None or not state.sql_validated.safe:
        return _to_failure(state, started, status=QueryStatus.REFUSED,
                           code=ErrorCode.SQL_UNSAFE)

    # 4. OPA authz on the validated SQL's table set
    state = await node_opa.run(state)
    if state.opa is not None and not state.opa.allow:
        return _to_failure(state, started, status=QueryStatus.REFUSED,
                           code=ErrorCode.OPA_DENIED)

    # 4b. Apply OPA row-filter obligations to the validated SQL.
    state = _apply_opa_obligations(state)

    # 5. Execute
    state = await node_execute.run(state)
    if state.errors and state.execution is None:
        return _to_failure(state, started, status=QueryStatus.ERROR,
                           code=ErrorCode.SQL_EXECUTION_FAILED)

    # 6. NL explanation (Phase 3, non-blocking)
    state = await node_explain.run(state)

    # 7. Output PII mask on result rows + explanation (Phase 3)
    state = await node_output_mask.run(state)

    latency_ms = int((time.perf_counter() - started) * 1000)
    resp = QueryResponse(
        trace_id=str(state.trace_id),
        status=QueryStatus.OK,
        sql=state.sql_validated.sql,
        result=ResultPayload(
            columns=state.execution.columns,
            rows=state.execution.rows,
            row_count=state.execution.row_count,
            truncated=state.execution.truncated,
        ),
        explanation=(state.explanation.text if state.explanation else None) or None,
        tables_used=state.sql_validated.tables_used,
        model=node_sql_generate.PROMPT_VERSION,
        prompt_version=node_sql_generate.PROMPT_VERSION,
        cost_usd=0.0,
        latency_ms=latency_ms,
        output_mask=(
            state.output_mask.model_dump() if state.output_mask else {}
        ),
        feedback_url="/api/v1/feedback",
    )
    state.final = resp
    _emit(state)
    _record_metrics(resp, started)
    return resp


def _apply_opa_obligations(state: GraphState) -> GraphState:
    """Inject OPA obligations (e.g. row-filter) into validated SQL.

    Row-filter wraps the validated SQL with an EXISTS semi-join that
    restricts ``client`` rows to those owned by the current RM, e.g.:

        SELECT _rf.* FROM (<validated_sql>) AS _rf
        WHERE EXISTS (
          SELECT 1 FROM client WHERE client.cif_id = _rf.cif_id
          AND client.rm_owner = '<user_id>'
        )

    The wrapping is robust against arbitrary table aliases in the
    LLM-generated SQL because ``client`` is referenced by its real name in
    the EXISTS clause.  Skipped when ``client`` is not in the table list or
    the query does not output ``cif_id`` (pure aggregates).
    """
    if (state.opa is None
            or state.sql_validated is None
            or not state.sql_validated.safe):
        return state
    obligations = state.opa.obligations
    if not obligations:
        return state
    row_filter = obligations.get("row_filter")
    if not row_filter:
        return state
    sql = state.sql_validated.sql
    if "client" not in (state.sql_validated.tables_used or []):
        _log.debug("row_filter_skipped_no_client_table", sql_preview=sql[:80])
        return state

    # Use sqlglot to check whether the SELECT outputs cif_id (skip for
    # COUNT(*) / aggregate-only queries where row-filtering is meaningless).
    import sqlglot
    from sqlglot import expressions as exp
    try:
        tree = sqlglot.parse_one(sql, read="trino")
    except Exception:
        _log.warning("row_filter_parse_failed", sql_preview=sql[:120])
        return state

    if not isinstance(tree, exp.Select):
        return state

    # Build semi-join wrapper: the guaranteed column is cif_id (client PK).
    # If the query doesn't project cif_id, skip — it is an aggregate.
    output_cols = {c.alias_or_name.lower() for c in tree.expressions if hasattr(c, 'alias_or_name')}
    if "cif_id" not in output_cols:
        _log.debug("row_filter_skipped_no_cif_id_in_output",
                   cols=sorted(output_cols), sql_preview=sql[:120])
        return state

    wrapped = (
        f"SELECT _rf.* FROM ({sql}) AS _rf "
        f"WHERE EXISTS (SELECT 1 FROM client WHERE client.cif_id = _rf.cif_id AND {row_filter})"
    )
    state.sql_validated.sql = wrapped
    _log.info("row_filter_applied", row_filter=row_filter,
              sql_preview=wrapped[:300])
    return state


def _to_failure(
    state: GraphState,
    started: float,
    *,
    status: QueryStatus,
    code: ErrorCode = ErrorCode.INTERNAL,
) -> QueryResponse:
    latency_ms = int((time.perf_counter() - started) * 1000)
    msg = "; ".join(f"[{e.node}] {e.message}" for e in state.errors) or "unknown"
    details: dict = {}
    if state.sql_validated is not None:
        details["violations"] = state.sql_validated.violations
    if state.opa is not None:
        details["opa_reasons"] = state.opa.reasons
    if state.pii is not None and (state.pii.has_pii or state.pii.injection_suspected):
        details["pii_entity_types"] = sorted({e.entity_type for e in state.pii.entities})
        details["injection_signals"] = state.pii.injection_signals
    resp = QueryResponse(
        trace_id=str(state.trace_id),
        status=status,
        latency_ms=latency_ms,
        error=ErrorPayload(
            code=code, message=msg, trace_id=str(state.trace_id), details=details,
        ),
    )
    state.final = resp
    _emit(state)
    _record_metrics(resp, started)
    return resp


def _record_metrics(resp: QueryResponse, started: float) -> None:
    """Phase 4 — emit Prometheus metrics for every terminal response."""
    LATENCY_SECONDS.observe(max(0.0, time.perf_counter() - started))
    error_code = resp.error.code.value if resp.error else "none"
    REQUESTS_TOTAL.labels(status=resp.status.value, error_code=error_code).inc()
    if resp.status == QueryStatus.REFUSED and resp.error:
        SECURITY_BLOCKS_TOTAL.labels(reason=resp.error.code.value).inc()


def _emit(state: GraphState) -> None:
    try:
        emit_trace(
            trace_id=str(state.trace_id),
            name="text2sql.query",
            user_id=state.request.user.id,
            payload={
                "status": state.final.status if state.final else "unknown",
                "spans": [s.model_dump(mode="json") for s in state.spans],
                "errors": [e.model_dump() for e in state.errors],
                "tables_used": state.sql_validated.tables_used if state.sql_validated else [],
                "row_count": state.execution.row_count if state.execution else 0,
                "repair_attempts": state.repair_attempts,
                "opa_allow": state.opa.allow if state.opa else None,
                "schema_fallback": state.schema_link.used_fallback if state.schema_link else None,
            },
        )
    except Exception as e:  # noqa: BLE001
        _log.warning("emit_trace_failed", error=str(e))
