"""Phase 3 E2E — HITL feedback + NL explanation + output mask + Golden Set.

Run with:  pytest -m phase3   (skipped automatically if stack is down)
Acceptance bar (ADR-0005):
  * /api/v1/query OK responses include an `explanation` (non-empty when
    EXPLAIN_ENABLED) and an `output_mask` summary block.
  * /api/v1/feedback accepts thumbs_up/down + correction; sink is "argilla"
    when ARGILLA_ENABLED=true is set, "local-jsonl" otherwise.
  * Golden Set pass rate ≥ 90% (gates the build).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

LANGGRAPH_URL = os.environ.get("LANGGRAPH_URL", "http://localhost:8080")


def _stack_up() -> bool:
    try:
        return httpx.get(f"{LANGGRAPH_URL}/healthz", timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _stack_up(),
    reason=f"langgraph-app not reachable at {LANGGRAPH_URL} — run `make up-min` first",
)


def _query(question: str, role: str = "RM") -> dict:
    body = {
        "trace_id": str(uuid4()),
        "user": {"id": "eval@bank", "role": role, "business_unit": "CIB-APAC"},
        "question": question,
    }
    r = httpx.post(f"{LANGGRAPH_URL}/api/v1/query", json=body, timeout=180.0)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.phase3
@pytest.mark.e2e
def test_query_response_carries_explanation_and_mask() -> None:
    body = _query("How many active clients are there?")
    assert body["status"] == "ok", body
    assert "output_mask" in body and body["output_mask"].get("enabled") in (True, False)
    assert body.get("feedback_url") == "/api/v1/feedback"
    # Explanation may be empty if EXPLAIN_ENABLED=false; otherwise non-empty.
    assert "explanation" in body


@pytest.mark.phase3
@pytest.mark.e2e
def test_feedback_thumbs_up_accepted() -> None:
    body = _query("How many active clients are there?")
    payload = {
        "trace_id": body["trace_id"],
        "user_id": "eval@bank",
        "rating": "thumbs_up",
        "question": "How many active clients are there?",
        "sql": body.get("sql"),
        "tables_used": body.get("tables_used", []),
    }
    r = httpx.post(f"{LANGGRAPH_URL}/api/v1/feedback", json=payload, timeout=10.0)
    assert r.status_code == 200, r.text
    fb = r.json()
    assert fb["accepted"] is True
    assert fb["sink"] in ("argilla", "local-jsonl")
    assert fb["record_id"]


@pytest.mark.phase3
@pytest.mark.e2e
def test_feedback_correction_accepted() -> None:
    payload = {
        "trace_id": str(uuid4()),
        "user_id": "eval@bank",
        "rating": "correction",
        "question": "How many active clients?",
        "sql": "SELECT count(*) FROM client",
        "corrected_sql": "SELECT count(*) FROM client WHERE is_active",
        "comment": "must filter on is_active",
        "tags": ["golden-candidate"],
    }
    r = httpx.post(f"{LANGGRAPH_URL}/api/v1/feedback", json=payload, timeout=10.0)
    assert r.status_code == 200, r.text


@pytest.mark.phase3
@pytest.mark.e2e
def test_golden_set_passes_threshold(tmp_path: Path) -> None:
    """Run the golden-set harness against the live stack."""
    repo = Path(__file__).resolve().parents[2]
    report = tmp_path / "report.json"
    cmd = [
        sys.executable,
        str(repo / "tests" / "eval" / "run_eval.py"),
        "--base-url", LANGGRAPH_URL,
        "--golden", str(repo / "tests" / "eval" / "golden_set.yaml"),
        "--report", str(report),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    print(proc.stdout)
    print(proc.stderr, file=sys.stderr)
    assert report.exists(), "report not written"
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["pass_rate"] >= data["threshold"], (
        f"golden-set pass rate {data['pass_rate']:.1%} < threshold "
        f"{data['threshold']:.0%}\n"
        + json.dumps(data["cases"], indent=2)
    )
