"""C2 — Chainlit ↔ LangGraph contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from text2sql_contracts.errors import ErrorPayload


class UserRole(StrEnum):
    RM = "RM"
    Risk = "Risk"
    Compliance = "Compliance"
    Ops = "Ops"
    Finance = "Finance"
    Admin = "Admin"


class User(BaseModel):
    id: str
    role: UserRole
    business_unit: str


class Preferences(BaseModel):
    row_limit: int = Field(1000, ge=1, le=10_000)
    explain_in: str = Field("en", pattern="^(en|zh)$")


class QueryRequest(BaseModel):
    """C2 request body — `POST /api/v1/query`."""

    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    user: User
    session_id: str | None = None
    question: str = Field(..., min_length=1, max_length=2000)
    clarifications: list[dict[str, Any]] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)


class QueryStatus(StrEnum):
    OK = "ok"
    NEED_CLARIFY = "need_clarify"
    NEED_APPROVAL = "need_approval"
    REFUSED = "refused"
    ERROR = "error"


class ResultPayload(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False


class ExecutionResult(BaseModel):
    """Internal — output of the `execute` node."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False
    elapsed_ms: int = 0


class QueryResponse(BaseModel):
    """C2 response body."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    status: QueryStatus
    sql: str | None = None
    result: ResultPayload | None = None
    explanation: str | None = None
    metrics_used: list[str] = Field(default_factory=list)
    tables_used: list[str] = Field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    error: ErrorPayload | None = None
    # Phase 3 — non-breaking extensions
    output_mask: dict[str, Any] = Field(default_factory=dict)
    feedback_url: str | None = None
