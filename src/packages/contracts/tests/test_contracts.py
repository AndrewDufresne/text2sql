"""Contract round-trip tests — guarantees the wire format never silently drifts."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from text2sql_contracts import (
    FailureMode,
    FeedbackRating,
    FeedbackRequest,
    FeedbackResponse,
    GraphState,
    NodeName,
    QueryRequest,
    QueryResponse,
    QueryStatus,
    ResultPayload,
    User,
    UserRole,
)


@pytest.fixture
def sample_request() -> QueryRequest:
    return QueryRequest(
        trace_id=uuid4(),
        user=User(id="alice@bank", role=UserRole.RM, business_unit="CIB-APAC"),
        question="List the top 5 clients by AUM",
    )


def test_query_request_roundtrip(sample_request: QueryRequest) -> None:
    raw = sample_request.model_dump_json()
    parsed = QueryRequest.model_validate_json(raw)
    assert parsed == sample_request


def test_query_request_rejects_extra_fields() -> None:
    with pytest.raises(ValueError):
        QueryRequest.model_validate(
            {
                "trace_id": str(uuid4()),
                "user": {"id": "a", "role": "RM", "business_unit": "x"},
                "question": "q",
                "evil_field": "boom",
            }
        )


def test_query_response_minimal_ok() -> None:
    resp = QueryResponse(
        trace_id=str(uuid4()),
        status=QueryStatus.OK,
        sql="SELECT 1",
        result=ResultPayload(columns=["c"], rows=[[1]], row_count=1),
        model="ollama/qwen2.5:7b",
        prompt_version="sql_generate@v1",
    )
    payload = json.loads(resp.model_dump_json())
    assert payload["status"] == "ok"
    assert payload["result"]["row_count"] == 1


def test_graph_state_append_only_spans(sample_request: QueryRequest) -> None:
    state = GraphState(trace_id=sample_request.trace_id, request=sample_request)
    state.start_span(NodeName.SQL_GENERATE)
    state.start_span(NodeName.SQL_VALIDATE)
    assert [s.node for s in state.spans] == [
        NodeName.SQL_GENERATE,
        NodeName.SQL_VALIDATE,
    ]


def test_graph_state_serializable(sample_request: QueryRequest) -> None:
    state = GraphState(trace_id=sample_request.trace_id, request=sample_request)
    raw = state.model_dump_json()
    again = GraphState.model_validate_json(raw)
    assert again.trace_id == state.trace_id


# ---------- Phase 3 ----------

def test_feedback_request_roundtrip() -> None:
    req = FeedbackRequest(
        trace_id=str(uuid4()),
        user_id="alice@bank",
        rating=FeedbackRating.THUMBS_DOWN,
        question="how many active clients?",
        sql="SELECT count(*) FROM client",
        corrected_sql="SELECT count(*) FROM client WHERE is_active",
        comment="missed the WHERE",
    )
    assert FeedbackRequest.model_validate_json(req.model_dump_json()) == req


def test_feedback_request_rejects_extra_fields() -> None:
    with pytest.raises(ValueError):
        FeedbackRequest.model_validate(
            {
                "trace_id": str(uuid4()),
                "user_id": "x",
                "rating": "thumbs_up",
                "question": "q",
                "evil": True,
            }
        )


def test_feedback_response_minimal() -> None:
    r = FeedbackResponse(accepted=True, sink="argilla", record_id="abc")
    assert r.accepted is True
    assert r.sink == "argilla"


def test_query_response_phase3_extensions() -> None:
    resp = QueryResponse(
        trace_id=str(uuid4()),
        status=QueryStatus.OK,
        sql="SELECT 1",
        result=ResultPayload(columns=["c"], rows=[[1]], row_count=1),
        explanation="There is one row.",
        output_mask={"enabled": True, "cells_masked": 0},
        feedback_url="/api/v1/feedback",
    )
    payload = json.loads(resp.model_dump_json())
    assert payload["explanation"] == "There is one row."
    assert payload["output_mask"]["enabled"] is True
    assert payload["feedback_url"] == "/api/v1/feedback"


# ---------- Phase 3.1 — full Argilla schema ----------

def test_feedback_request_phase31_full_roundtrip() -> None:
    req = FeedbackRequest(
        trace_id=str(uuid4()),
        user_id="alice@bank",
        rating=FeedbackRating.CORRECTION,
        question="top 5 active clients by AUM",
        sql="SELECT * FROM client",
        corrected_sql="SELECT cif_id FROM client WHERE is_active ORDER BY aum DESC LIMIT 5",
        comment="missed WHERE",
        result_preview="| cif | aum |\n|---|---|\n| 1 | 100 |",
        explanation="Returns the 5 highest-AUM active clients.",
        failure_mode=FailureMode.WRONG_FILTER,
        user_role="RM",
        business_unit="CIB-APAC",
        model="deepseek/deepseek-chat",
        prompt_version="sql_generate@phase2-v1",
        metrics_used=["aum"],
        tables_used=["client"],
        cost_usd=0.001234,
        latency_ms=2100,
        question_embedding=[0.1, 0.2, 0.3],
    )
    parsed = FeedbackRequest.model_validate_json(req.model_dump_json())
    assert parsed == req
    assert parsed.failure_mode == FailureMode.WRONG_FILTER
    assert parsed.cost_usd == pytest.approx(0.001234)
    assert parsed.question_embedding == [0.1, 0.2, 0.3]


def test_failure_mode_enum_strict() -> None:
    # invalid label must reject (strict StrEnum on Pydantic v2).
    with pytest.raises(ValueError):
        FeedbackRequest.model_validate(
            {
                "trace_id": str(uuid4()),
                "user_id": "x",
                "rating": "thumbs_down",
                "question": "q",
                "failure_mode": "not_a_valid_mode",
            }
        )
