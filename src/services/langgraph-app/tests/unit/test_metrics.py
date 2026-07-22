"""Phase 4 — metrics + /metrics endpoint tests.

Pure unit tests; no Docker / OTel collector required.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from text2sql_contracts import (
    FeedbackRating,
    FeedbackRequest,
    QueryRequest,
    QueryStatus,
    User,
    UserRole,
)

from app import graph as graph_mod
from app import metrics as metrics_mod
from app.clients import argilla_client, pgvector_store
from app.main import app
from app.nodes import execute as exec_node
from app.nodes import explain as explain_node
from app.nodes import output_mask as mask_node
from app.nodes import pii_guard as pii_node
from app.nodes import schema_link as link_node
from app.nodes import sql_generate as gen_node


@pytest.fixture(autouse=True)
def _stub_externals(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_pii(_text: str, **_: Any) -> list[dict[str, Any]]:
        return []

    async def fake_search(_q: str, top_k: int = 3) -> list[dict[str, Any]]:
        return [
            {"table": "client", "description": "customer master",
             "columns": ["cif_id", "is_active"], "score": 0.9}
        ]

    async def stub_explain(**_: Any) -> tuple[str, dict[str, Any]]:
        return "stub", {"model": "stub"}

    monkeypatch.setattr(pii_node, "analyze", no_pii)
    monkeypatch.setattr(mask_node, "analyze", no_pii)
    monkeypatch.setattr(explain_node, "generate_explanation", stub_explain)
    monkeypatch.setattr(pgvector_store, "search", fake_search)
    monkeypatch.setattr(graph_mod, "emit_trace", lambda **_: None)
    from app.settings import get_settings
    monkeypatch.setattr(get_settings(), "opa_enabled", False)


def test_metrics_endpoint_exposes_phase4_metric_names() -> None:
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    for name in (
        "text2sql_requests_total",
        "text2sql_request_latency_seconds",
        "text2sql_security_blocks_total",
        "text2sql_self_repair_total",
        "text2sql_feedback_total",
        "text2sql_llm_calls_total",
    ):
        assert name in body, f"missing metric {name}"


async def test_query_increments_request_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_generate(**_: Any):
        return "SELECT count(*) AS n FROM client LIMIT 1", {"model": "stub"}

    async def fake_execute(**_: Any):
        return ["n"], [[1]], 1, 2

    monkeypatch.setattr(gen_node, "generate_sql", fake_generate)
    monkeypatch.setattr(exec_node, "execute_sql", fake_execute)

    before = metrics_mod.REQUESTS_TOTAL.labels(
        status="ok", error_code="none"
    )._value.get()

    req = QueryRequest(
        trace_id=uuid4(),
        user=User(id="alice@bank", role=UserRole.RM, business_unit="CIB-APAC"),
        question="how many clients?",
    )
    resp = await graph_mod.run_query(req)
    assert resp.status == QueryStatus.OK

    after = metrics_mod.REQUESTS_TOTAL.labels(
        status="ok", error_code="none"
    )._value.get()
    assert after == before + 1


async def test_unsafe_sql_increments_security_block(monkeypatch: pytest.MonkeyPatch) -> None:
    async def always_drop(**_: Any):
        return "DROP TABLE client", {"model": "stub"}

    monkeypatch.setattr(gen_node, "generate_sql", always_drop)

    before = metrics_mod.SECURITY_BLOCKS_TOTAL.labels(reason="SQL_UNSAFE")._value.get()

    req = QueryRequest(
        trace_id=uuid4(),
        user=User(id="alice@bank", role=UserRole.RM, business_unit="CIB-APAC"),
        question="how many clients?",
    )
    resp = await graph_mod.run_query(req)
    assert resp.status == QueryStatus.REFUSED

    after = metrics_mod.SECURITY_BLOCKS_TOTAL.labels(reason="SQL_UNSAFE")._value.get()
    assert after == before + 1


async def test_feedback_endpoint_increments_counter(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from app.settings import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "argilla_enabled", False)
    monkeypatch.setattr(s, "feedback_local_path", str(tmp_path / "fb.jsonl"))

    before = metrics_mod.FEEDBACK_TOTAL.labels(sink="local-jsonl", rating="thumbs_up")._value.get()

    body = {
        "trace_id": str(uuid4()),
        "user_id": "alice@bank",
        "rating": "thumbs_up",
        "question": "q",
        "sql": "SELECT 1",
    }
    client = TestClient(app)
    r = client.post("/api/v1/feedback", json=body)
    assert r.status_code == 200, r.text
    sink = r.json()["sink"]
    assert sink == "local-jsonl"
    after = metrics_mod.FEEDBACK_TOTAL.labels(sink="local-jsonl", rating="thumbs_up")._value.get()
    assert after == before + 1
