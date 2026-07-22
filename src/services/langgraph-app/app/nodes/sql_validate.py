"""Node 2 — sql_validate.

Pure-Python AST validation via sqlglot. NO network calls; deterministic.
This is the security floor: even Phase 1 enforces read-only + table allowlist
+ mandatory LIMIT (per io-contracts §S1).
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlglot
from sqlglot import expressions as exp

from text2sql_contracts import (
    GraphState,
    NodeError,
    NodeName,
    SqlValidationResult,
)
from text2sql_contracts.errors import ErrorCode

from app.observability import get_logger
from app.schema_catalog import ALLOWED_TABLES

_log = get_logger(__name__)

# Statement classes that are NEVER allowed (extend cautiously)
_FORBIDDEN_STMT_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,        # Covers ALTER TABLE / ALTER COLUMN in sqlglot >= 26
    exp.AlterColumn,
    exp.Merge,
    exp.Command,    # CALL/SET/USE/etc.
    exp.TruncateTable,
)


def validate(sql: str, *, allowed_tables: frozenset[str] = ALLOWED_TABLES,
             default_limit: int = 1000) -> SqlValidationResult:
    """Validate one SQL string. Pure function — easy to unit-test."""
    sql = (sql or "").strip().rstrip(";").strip()
    violations: list[str] = []
    tables_used: list[str] = []

    if not sql:
        return SqlValidationResult(safe=False, sql=sql, violations=["empty_sql"])

    # 1. Parse
    try:
        statements = sqlglot.parse(sql, read="trino")
    except Exception as e:  # noqa: BLE001
        return SqlValidationResult(
            safe=False, sql=sql, violations=[f"parse_error: {e}"]
        )

    if len(statements) != 1:
        violations.append(f"expected_single_statement_got_{len(statements)}")

    stmt = statements[0] if statements else None
    if stmt is None:
        return SqlValidationResult(safe=False, sql=sql, violations=violations + ["no_statement"])

    # 2. Statement type whitelist (must be SELECT-rooted)
    if isinstance(stmt, _FORBIDDEN_STMT_TYPES):
        violations.append(f"forbidden_statement: {type(stmt).__name__}")
    if not isinstance(stmt, (exp.Select, exp.Selectable, exp.Union)):
        # `exp.Select` / `exp.Union` cover SELECT and `WITH ... SELECT` via Subqueryable
        if not isinstance(stmt, exp.With):
            violations.append(f"non_select_root: {type(stmt).__name__}")

    # 3. Walk AST: collect tables & catch nested forbidden ops
    cte_names: set[str] = set()
    for node in stmt.walk():
        if isinstance(node, exp.CTE):
            alias = node.args.get("alias")
            if alias is not None and getattr(alias, "name", None):
                cte_names.add(alias.name)
    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN_STMT_TYPES) and node is not stmt:
            violations.append(f"nested_forbidden: {type(node).__name__}")
        if isinstance(node, exp.Table):
            name = node.name
            if name and name not in cte_names:
                tables_used.append(name)

    # 4. Allowlist
    for t in tables_used:
        if t not in allowed_tables:
            violations.append(f"table_not_allowed: {t}")

    # 5. Mandatory LIMIT — inject a safety wrapper when the top-level
    #    statement has no explicit LIMIT.  Wrapping via a subquery works
    #    for SELECT, CTE (WITH), and UNION alike.
    _needs_limit = _top_level_missing_limit(stmt)
    if _needs_limit:
        wrapped = sqlglot.parse_one(
            f"SELECT * FROM ({stmt.sql(dialect='trino')}) AS _t LIMIT {default_limit}",
            read="trino",
        )
        sql = wrapped.sql(dialect="trino")

    safe = not violations
    return SqlValidationResult(
        safe=safe,
        sql=sql,
        tables_used=sorted(set(tables_used)),
        violations=violations,
    )


def _top_level_missing_limit(stmt: exp.Expression) -> bool:
    """Return True when the top-level statement needs a safety LIMIT injected.

    Only wraps SELECT, CTE (WITH … SELECT) and UNION — these are the only
    statement types that survive the validation allowlist.  Forbidden types
    (DROP, INSERT, etc.) are caught by validation and must NOT be wrapped
    because they cannot appear inside a subquery.
    """
    if isinstance(stmt, exp.Select):
        return stmt.args.get("limit") is None
    if isinstance(stmt, exp.With):
        inner = stmt.this
        if isinstance(inner, exp.Select):
            return inner.args.get("limit") is None
        return True
    if isinstance(stmt, exp.Union):
        # Check the leftmost leaf; if it has a LIMIT, assume intentional.
        left = stmt.left
        while isinstance(left, exp.Union):
            left = left.left
        if isinstance(left, exp.Select):
            return left.args.get("limit") is None
        return True
    # Non-selectable root (e.g. DROP TABLE) — validation will reject it;
    # do NOT attempt to wrap it as a subquery (that would be a parse error).
    return False


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.SQL_VALIDATE)
    started = span.started_at
    try:
        if state.sql_draft is None:
            state.sql_validated = SqlValidationResult(safe=False, sql="", violations=["no_draft"])
        else:
            state.sql_validated = validate(state.sql_draft)
        span.attrs["safe"] = state.sql_validated.safe
        span.attrs["violations"] = state.sql_validated.violations
        span.attrs["tables_used"] = state.sql_validated.tables_used
        if not state.sql_validated.safe:
            span.status = "error"
            state.errors.append(
                NodeError(
                    node=NodeName.SQL_VALIDATE.value,
                    code=ErrorCode.SQL_UNSAFE,
                    message="; ".join(state.sql_validated.violations),
                )
            )
        _log.info(
            "sql_validate_done",
            trace_id=str(state.trace_id),
            safe=state.sql_validated.safe,
            violations=state.sql_validated.violations,
        )
    finally:
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
    return state
