"""Unit tests for schema_link node.

We mock the pgvector_store so the test doesn't need TEI / Postgres.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from text2sql_contracts import GraphState, QueryRequest, User, UserRole

from app.clients import pgvector_store
from app.nodes import schema_link


def _state(question: str) -> GraphState:
    req = QueryRequest(
        trace_id=uuid4(),
        user=User(id="u@bank", role=UserRole.RM, business_unit="CIB-APAC"),
        question=question,
    )
    return GraphState(trace_id=req.trace_id, request=req)


@pytest.fixture(autouse=True)
def stub_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop() -> None:
        return None

    monkeypatch.setattr(pgvector_store, "ensure_index_seeded", noop)


async def test_search_results_attached(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(_q: str, top_k: int = 3) -> list[dict[str, Any]]:
        return [
            {"table": "exposure", "description": "credit exposures",
             "columns": ["pd_bps", "drawn_usd"], "score": 0.91},
            {"table": "client", "description": "customer master",
             "columns": ["cif_id"], "score": 0.55},
        ]

    monkeypatch.setattr(pgvector_store, "search", fake_search)
    s = await schema_link.run(_state("average pd_bps by industry"))
    assert s.schema_link is not None
    assert not s.schema_link.used_fallback
    tables = [c.table for c in s.schema_link.cards]
    assert tables == ["exposure", "client"]


async def test_search_failure_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        raise RuntimeError("pgvector down")

    monkeypatch.setattr(pgvector_store, "search", boom)
    s = await schema_link.run(_state("anything"))
    assert s.schema_link.used_fallback
    # Fallback returns ALL cards (Phase 5 extended domain: 11 tables)
    tables = sorted(c.table for c in s.schema_link.cards)
    assert len(tables) == 11
    assert "client" in tables
    assert "exposure" in tables


async def test_disabled_uses_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "schema_link_enabled", False)
    s = await schema_link.run(_state("x"))
    assert s.schema_link.used_fallback
    assert len(s.schema_link.cards) == 11  # Phase 5: extended domain
