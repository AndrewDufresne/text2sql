"""Error envelopes (see io-contracts §0.2)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHORIZED = "UNAUTHORIZED"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    TIMEOUT = "TIMEOUT"
    INTERNAL = "INTERNAL"
    SQL_UNSAFE = "SQL_UNSAFE"
    SQL_EXECUTION_FAILED = "SQL_EXECUTION_FAILED"
    LLM_FAILED = "LLM_FAILED"
    # Phase 2
    PII_DETECTED = "PII_DETECTED"
    OPA_DENIED = "OPA_DENIED"
    SCHEMA_LINK_FAILED = "SCHEMA_LINK_FAILED"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    # Phase 3
    EXPLAIN_FAILED = "EXPLAIN_FAILED"
    OUTPUT_MASK_FAILED = "OUTPUT_MASK_FAILED"
    FEEDBACK_REJECTED = "FEEDBACK_REJECTED"


class ErrorPayload(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class NodeError(BaseModel):
    """Error attached to a specific LangGraph node execution."""

    node: str
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
