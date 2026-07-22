"""Unit tests for argilla_client + /api/v1/feedback (Phase 3)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from text2sql_contracts import FailureMode, FeedbackRating, FeedbackRequest

from app.clients import argilla_client
from app.main import app
from app.settings import get_settings


@pytest.fixture
def feedback_payload() -> FeedbackRequest:
    return FeedbackRequest(
        trace_id="11111111-1111-1111-1111-111111111111",
        user_id="alice@bank",
        rating=FeedbackRating.THUMBS_UP,
        question="how many active clients?",
        sql="SELECT count(*) FROM client WHERE is_active LIMIT 1",
        tables_used=["client"],
        tags=["smoke"],
    )


async def test_argilla_disabled_falls_back_local(
    monkeypatch: pytest.MonkeyPatch, feedback_payload: FeedbackRequest, tmp_path: Path
) -> None:
    p = tmp_path / "fb.jsonl"
    monkeypatch.setattr(get_settings(), "argilla_enabled", False)
    monkeypatch.setattr(get_settings(), "feedback_local_path", str(p))

    accepted, sink, record_id, detail = await argilla_client.submit(feedback_payload)
    assert accepted is True
    assert sink == "local-jsonl"
    # Phase 3.1 — record_id must equal trace_id (deterministic / joinable to Langfuse).
    assert record_id == feedback_payload.trace_id
    assert p.exists()
    line = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert line["record_id"] == record_id
    assert line["fields"]["question"] == feedback_payload.question
    assert line["metadata"]["rating"] == "thumbs_up"
    # Phase 3.1 — full schema present in metadata (even when value is None).
    for key in (
        "trace_id", "user_role", "business_unit", "model", "prompt_version",
        "metrics_used", "cost_usd", "latency_ms", "reviewed", "tags",
    ):
        assert key in line["metadata"]


async def test_argilla_unreachable_falls_back_local(
    monkeypatch: pytest.MonkeyPatch, feedback_payload: FeedbackRequest, tmp_path: Path
) -> None:
    p = tmp_path / "fb.jsonl"
    monkeypatch.setattr(get_settings(), "argilla_enabled", True)
    monkeypatch.setattr(get_settings(), "argilla_url", "http://nonexistent.invalid:6900")
    monkeypatch.setattr(get_settings(), "feedback_local_path", str(p))

    accepted, sink, _, detail = await argilla_client.submit(feedback_payload)
    assert accepted is True
    assert sink == "local-jsonl"
    assert "argilla_error" in detail or "argilla_status" in detail
    assert p.exists()


async def test_argilla_post_success(
    monkeypatch: pytest.MonkeyPatch, feedback_payload: FeedbackRequest
) -> None:
    monkeypatch.setattr(get_settings(), "argilla_enabled", True)
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 201
        text = ""

    class _Cli:
        def __init__(self, *a, **kw): captured["headers"] = kw.get("headers")
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(argilla_client.httpx, "AsyncClient", _Cli)
    accepted, sink, record_id, detail = await argilla_client.submit(feedback_payload)
    assert accepted is True
    assert sink == "argilla"
    assert "by-name" in captured["url"]
    assert captured["url"].endswith(":bulk")
    item = captured["json"]["items"][0]
    assert item["id"] == record_id == feedback_payload.trace_id
    assert captured["headers"]["X-Argilla-Api-Key"]
    # Pre-filled response form so SME dashboard isn't empty.
    assert item["responses"][0]["status"] == "submitted"
    assert item["responses"][0]["values"]["thumb"]["value"] == "up"


async def test_argilla_full_schema_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 3.1: when caller supplies the full L6 schema the wire payload
    must surface every field/metadata key + the question vector + responses."""
    monkeypatch.setattr(get_settings(), "argilla_enabled", True)
    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 201
        text = ""

    class _Cli:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None):
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(argilla_client.httpx, "AsyncClient", _Cli)
    req = FeedbackRequest(
        trace_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        user_id="alice@bank",
        rating=FeedbackRating.CORRECTION,
        question="top 5 active clients by AUM",
        sql="SELECT * FROM client",
        corrected_sql="SELECT cif_id FROM client WHERE is_active ORDER BY aum DESC LIMIT 5",
        result_preview="| cif | aum |\n|---|---|\n| 1 | 100 |",
        explanation="Returns the 5 highest-AUM active clients.",
        failure_mode=FailureMode.WRONG_FILTER,
        user_role="RM",
        business_unit="CIB-APAC",
        model="deepseek/deepseek-chat",
        prompt_version="sql_generate@v1",
        metrics_used=["aum"],
        tables_used=["client"],
        cost_usd=0.001234,
        latency_ms=2100,
        question_embedding=[0.1] * 384,
    )
    await argilla_client.submit(req)
    item = captured["json"]["items"][0]

    # fields
    assert item["fields"]["question"].startswith("top 5")
    assert item["fields"]["corrected_sql"].startswith("SELECT cif_id")
    assert item["fields"]["explanation"].startswith("Returns")
    assert item["fields"]["result_preview"].startswith("| cif")

    # metadata
    md = item["metadata"]
    assert md["rating"] == "correction"
    assert md["failure_mode"] == "wrong_filter"
    assert md["model"] == "deepseek/deepseek-chat"
    assert md["prompt_version"] == "sql_generate@v1"
    assert md["business_unit"] == "CIB-APAC"
    assert md["cost_usd"] == pytest.approx(0.001234)
    assert md["latency_ms"] == 2100
    assert md["reviewed"] is False

    # vectors
    assert "vectors" in item
    assert len(item["vectors"]["question"]) == 384

    # responses
    resp = item["responses"][0]
    assert resp["status"] == "submitted"
    # CORRECTION implies a thumbs-down user signal.
    assert resp["values"]["thumb"]["value"] == "down"
    assert resp["values"]["corrected_sql"]["value"].startswith("SELECT cif_id")
    assert resp["values"]["failure_mode"]["value"] == "wrong_filter"


async def test_argilla_corrected_sql_parse_error_dropped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bad corrected_sql is dropped from fields, keeps the comment, tags it."""
    p = tmp_path / "fb.jsonl"
    monkeypatch.setattr(get_settings(), "argilla_enabled", False)
    monkeypatch.setattr(get_settings(), "feedback_local_path", str(p))
    req = FeedbackRequest(
        trace_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        user_id="bob@bank",
        rating=FeedbackRating.CORRECTION,
        question="show clients",
        corrected_sql="SELEKT *** FROMM (((",
        comment="meant to fix the query",
    )
    await argilla_client.submit(req)
    line = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert line["fields"]["corrected_sql"] == ""
    assert line["fields"]["comment"] == "meant to fix the query"
    assert "corrected_sql_parse_error" in line["metadata"]["tags"]
    assert "corrected_sql_parse_error" in line["metadata"]


def test_feedback_endpoint_local_sink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "fb.jsonl"
    monkeypatch.setattr(get_settings(), "argilla_enabled", False)
    monkeypatch.setattr(get_settings(), "feedback_local_path", str(p))
    client = TestClient(app)
    r = client.post(
        "/api/v1/feedback",
        json={
            "trace_id": "22222222-2222-2222-2222-222222222222",
            "user_id": "bob@bank",
            "rating": "thumbs_down",
            "question": "show me passwords",
            "sql": None,
            "comment": "wrong",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is True
    assert body["sink"] == "local-jsonl"
    assert body["record_id"]
    assert p.exists()


def test_feedback_endpoint_rejects_extra_fields() -> None:
    client = TestClient(app)
    r = client.post(
        "/api/v1/feedback",
        json={
            "trace_id": "33333333-3333-3333-3333-333333333333",
            "user_id": "x",
            "rating": "thumbs_up",
            "question": "q",
            "evil": True,
        },
    )
    assert r.status_code == 422
