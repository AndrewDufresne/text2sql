"""C13 — HITL feedback contract (LangGraph ↔ Argilla).

Phase 3.1 — schema aligned with `docs/layers/L6-hitl.md` §2.1.
Backward-compatible: every new field is optional / default-empty so existing
callers (Chainlit's minimal payload) keep working untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeedbackRating(StrEnum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    CORRECTION = "correction"  # explicit golden-set candidate


class FailureMode(StrEnum):
    """L6 §2.1 `failure_mode` label set."""

    WRONG_METRIC = "wrong_metric"
    WRONG_JOIN = "wrong_join"
    WRONG_FILTER = "wrong_filter"
    HALLUCINATION = "hallucination"
    PERF = "perf"
    OTHER = "other"


class FeedbackRequest(BaseModel):
    """Inbound payload to `POST /api/v1/feedback`."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    user_id: str
    rating: FeedbackRating

    # The fields below mirror the original turn so the record is self-contained
    # (Argilla / Golden Set should not need to join back to a trace store).
    question: str = Field(..., min_length=1, max_length=2000)
    sql: str | None = None
    corrected_sql: str | None = None
    comment: str | None = Field(default=None, max_length=2000)
    tables_used: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # ---- Phase 3.1 (full L6 schema) ----
    # Surfaced into Argilla `fields` so SME can review without joining trace store.
    result_preview: str | None = Field(
        default=None,
        max_length=4000,
        description="Top-N rows preview (must be PII-masked already).",
    )
    explanation: str | None = Field(
        default=None,
        max_length=4000,
        description="NL explanation produced by the explain node.",
    )

    # Surfaced into Argilla `metadata` (mirrors Langfuse field names for joins).
    failure_mode: FailureMode | None = None
    user_role: str | None = None
    business_unit: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    metrics_used: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: int = 0

    # Optional question embedding (e.g. `bge-*`); when absent the Argilla
    # client writes the record without the vector — Argilla still accepts it.
    question_embedding: list[float] | None = Field(default=None, repr=False)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    record_id: str | None = None
    sink: str = Field(..., description="argilla | local-jsonl | dropped")
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detail: dict[str, Any] = Field(default_factory=dict)
