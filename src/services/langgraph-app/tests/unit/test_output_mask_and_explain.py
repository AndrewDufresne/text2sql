"""Unit tests for output_mask + explain nodes (Phase 3)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from text2sql_contracts import (
    ExecutionResult,
    GraphState,
    QueryRequest,
    SqlValidationResult,
    User,
    UserRole,
)

from app.nodes import explain as explain_node
from app.nodes import output_mask as mask_node


def _state_with_rows(rows: list[list[Any]]) -> GraphState:
    req = QueryRequest(
        trace_id=uuid4(),
        user=User(id="alice@bank", role=UserRole.RM, business_unit="CIB-APAC"),
        question="dummy",
    )
    s = GraphState(trace_id=req.trace_id, request=req)
    s.sql_validated = SqlValidationResult(safe=True, sql="SELECT 1", tables_used=["client"])
    s.execution = ExecutionResult(
        columns=["name", "email"], rows=rows, row_count=len(rows), truncated=False
    )
    return s


async def test_output_mask_redacts_email(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_analyze(text: str, **_: Any) -> list[dict[str, Any]]:
        if "@" in text:
            i = text.index("@")
            start = text.rfind(" ", 0, i) + 1
            end = text.find(" ", i)
            end = end if end != -1 else len(text)
            return [{"entity_type": "EMAIL_ADDRESS", "start": start, "end": end, "score": 0.99}]
        return []

    monkeypatch.setattr(mask_node, "analyze", fake_analyze)

    state = _state_with_rows([["Alice", "alice@example.com"], ["Bob", "bob@bank.io"]])
    state = await mask_node.run(state)
    assert state.output_mask is not None
    assert state.output_mask.cells_masked == 2
    assert state.output_mask.entity_counts.get("EMAIL_ADDRESS") == 2
    assert "<EMAIL_ADDRESS>" in state.execution.rows[0][1]
    assert state.execution.rows[0][0] == "Alice"  # untouched


async def test_output_mask_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "output_mask_enabled", False)
    state = _state_with_rows([["alice@example.com"]])
    state = await mask_node.run(state)
    assert state.output_mask is not None
    assert state.output_mask.enabled is False
    assert state.output_mask.cells_masked == 0
    # No mutation
    assert state.execution.rows[0][0] == "alice@example.com"


async def test_output_mask_non_blocking_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(_text: str, **_: Any) -> list[dict[str, Any]]:
        raise RuntimeError("presidio gone")

    monkeypatch.setattr(mask_node, "analyze", boom)
    state = _state_with_rows([["alice@example.com"]])
    state = await mask_node.run(state)
    # Failure recorded but state.output_mask still populated and execution preserved.
    assert state.output_mask is not None
    assert any(e.code == "OUTPUT_MASK_FAILED" for e in state.errors)
    assert state.execution.rows[0][0] == "alice@example.com"


async def test_explain_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_explain(**_: Any) -> tuple[str, dict[str, Any]]:
        return "There are 18 active clients.", {"model": "stub", "prompt_tokens": 10, "completion_tokens": 6}

    monkeypatch.setattr(explain_node, "generate_explanation", fake_explain)
    state = _state_with_rows([[18]])
    state = await explain_node.run(state)
    assert state.explanation is not None
    assert state.explanation.failed is False
    assert "18" in state.explanation.text
    assert state.explanation.model == "stub"


async def test_explain_failure_non_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(**_: Any) -> tuple[str, dict[str, Any]]:
        raise RuntimeError("LLM down")

    monkeypatch.setattr(explain_node, "generate_explanation", boom)
    state = _state_with_rows([[1]])
    state = await explain_node.run(state)
    assert state.explanation is not None
    assert state.explanation.failed is True
    assert state.explanation.text == ""
    assert any(e.code == "EXPLAIN_FAILED" for e in state.errors)


async def test_explain_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "explain_enabled", False)
    state = _state_with_rows([[1]])
    state = await explain_node.run(state)
    assert state.explanation is not None
    assert state.explanation.text == ""
    assert state.explanation.failed is False
