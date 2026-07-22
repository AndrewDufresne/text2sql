"""C3 — LangGraph in-process state (see io-contracts §C3 and L5 §3)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from text2sql_contracts.errors import NodeError
from text2sql_contracts.query import ExecutionResult, QueryRequest, QueryResponse


class NodeName(StrEnum):
    """Phase 1 walking-skeleton: only 3 nodes. Extended in later phases."""

    SQL_GENERATE = "sql_generate"
    SQL_VALIDATE = "sql_validate"
    EXECUTE = "execute"
    # Phase 2+:
    PII_GUARD = "pii_guard"
    INTENT_GUARD = "intent_guard"
    SCHEMA_LINK = "schema_link"
    OPA_CHECK = "opa_check"
    DRY_RUN = "dry_run"
    EXPLAIN = "explain"
    EMIT = "emit"
    # Phase 3+:
    OUTPUT_MASK = "output_mask"


class SqlValidationResult(BaseModel):
    safe: bool
    sql: str
    tables_used: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


class PiiEntity(BaseModel):
    """One Presidio analyzer hit (or local-rule fallback)."""

    entity_type: str          # e.g. EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD
    start: int
    end: int
    score: float


class PiiAnalysis(BaseModel):
    """Result of `pii_guard` node on the inbound question."""

    has_pii: bool
    entities: list[PiiEntity] = Field(default_factory=list)
    sanitized_text: str | None = None  # text with entities replaced by <TYPE>
    injection_suspected: bool = False
    injection_signals: list[str] = Field(default_factory=list)


class SchemaCard(BaseModel):
    """A retrievable description of one table for RAG schema-linking."""

    table: str
    description: str
    columns: list[str] = Field(default_factory=list)
    score: float = 0.0       # cosine similarity at retrieval time


class SchemaLinkResult(BaseModel):
    cards: list[SchemaCard] = Field(default_factory=list)
    used_fallback: bool = False  # true when retrieval returned nothing


class OpaDecision(BaseModel):
    allow: bool
    reasons: list[str] = Field(default_factory=list)
    matched_policy: str | None = None
    obligations: dict[str, str] = Field(default_factory=dict)


class OutputMaskResult(BaseModel):
    """Result of `output_mask` node — what was redacted from result rows.

    Phase 3 keeps this minimal: counts per entity type + total cells touched.
    Useful in trace dashboards and as a smoke signal in evals.
    """

    enabled: bool = True
    cells_scanned: int = 0
    cells_masked: int = 0
    explanation_masked: bool = False
    entity_counts: dict[str, int] = Field(default_factory=dict)


class ExplanationResult(BaseModel):
    """Result of `explain` node — short NL explanation of the SQL/answer."""

    text: str
    model: str | None = None
    prompt_version: str | None = None
    elapsed_ms: int = 0
    failed: bool = False  # non-blocking: failure still returns OK


class Span(BaseModel):
    """Per-node observability span (mirrors Langfuse / OTel span)."""

    node: NodeName
    started_at: datetime
    ended_at: datetime | None = None
    status: Literal["ok", "error", "skipped"] = "ok"
    elapsed_ms: int = 0
    attrs: dict[str, Any] = Field(default_factory=dict)


class GraphState(BaseModel):
    """The single mutable object passed between LangGraph nodes.

    Append-only history (no node should rewrite a previous node's output).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_version: Literal["1.0"] = "1.0"

    # Inputs
    trace_id: UUID
    request: QueryRequest

    # Phase 1 working fields
    sql_draft: str | None = None
    sql_validated: SqlValidationResult | None = None
    execution: ExecutionResult | None = None

    # Phase 2 working fields
    pii: PiiAnalysis | None = None
    schema_link: SchemaLinkResult | None = None
    opa: OpaDecision | None = None
    repair_attempts: int = 0

    # Phase 3 working fields
    output_mask: OutputMaskResult | None = None
    explanation: ExplanationResult | None = None

    # Bookkeeping
    spans: list[Span] = Field(default_factory=list)
    errors: list[NodeError] = Field(default_factory=list)

    # Final response (set by the last node)
    final: QueryResponse | None = None

    def start_span(self, node: NodeName) -> Span:
        span = Span(node=node, started_at=datetime.now(timezone.utc))
        self.spans.append(span)
        return span
