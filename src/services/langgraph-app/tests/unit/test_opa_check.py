"""Unit tests for opa_check (offline fallback path)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from text2sql_contracts import (
    GraphState,
    QueryRequest,
    SqlValidationResult,
    User,
    UserRole,
)
from text2sql_contracts.errors import ErrorCode

from app.clients import opa_client
from app.nodes import opa_check
from app.settings import get_settings


@pytest.fixture(autouse=True)
def disable_remote_opa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the offline fallback so unit tests don't need OPA running."""
    s = get_settings()
    monkeypatch.setattr(s, "opa_enabled", False)


def _state_with_validated(role: UserRole, tables: list[str]) -> GraphState:
    req = QueryRequest(
        trace_id=uuid4(),
        user=User(id="u@bank", role=role, business_unit="CIB-APAC"),
        question="ignored",
    )
    st = GraphState(trace_id=req.trace_id, request=req)
    st.sql_validated = SqlValidationResult(
        safe=True,
        sql="SELECT 1",
        tables_used=tables,
        violations=[],
    )
    return st


async def test_rm_can_query_client() -> None:
    s = await opa_check.run(_state_with_validated(UserRole.RM, ["client"]))
    assert s.opa is not None and s.opa.allow
    assert s.errors == []


async def test_ops_blocked_from_exposure() -> None:
    s = await opa_check.run(_state_with_validated(UserRole.Ops, ["client", "exposure"]))
    assert s.opa is not None and not s.opa.allow
    assert any(e.code == ErrorCode.OPA_DENIED for e in s.errors)


async def test_unknown_role_denied() -> None:
    # Bypass the enum to simulate a wire-level surprise
    decision = opa_client._local_decision(  # noqa: SLF001
        {"user": {"role": "Hacker"}, "tables": ["client"], "ops": ["SELECT"]}
    )
    assert not decision["allow"]
    assert decision["matched_policy"] == "role_unknown"


async def test_op_not_allowed_denied() -> None:
    decision = opa_client._local_decision(  # noqa: SLF001
        {"user": {"role": "RM"}, "tables": ["client"], "ops": ["DROP"]}
    )
    assert not decision["allow"]
    assert decision["matched_policy"] == "ops_allowlist"


async def test_skipped_when_validation_unsafe() -> None:
    req = QueryRequest(
        trace_id=uuid4(),
        user=User(id="u@bank", role=UserRole.RM, business_unit="CIB-APAC"),
        question="x",
    )
    st = GraphState(trace_id=req.trace_id, request=req)
    st.sql_validated = SqlValidationResult(
        safe=False, sql="", tables_used=[], violations=["x"]
    )
    s = await opa_check.run(st)
    # No decision attached, no extra error, span marked skipped.
    assert s.opa is None
    assert s.spans[-1].status == "skipped"
