"""Text2SQL cross-layer I/O contracts (single source of truth).

Mirrors `docs/contracts/io-contracts.md`. Any change here MUST update the doc
in the same PR (and bump the relevant `schema_version`).
"""

from text2sql_contracts.errors import ErrorCode, ErrorPayload, NodeError
from text2sql_contracts.feedback import (
    FailureMode,
    FeedbackRating,
    FeedbackRequest,
    FeedbackResponse,
)
from text2sql_contracts.headers import REQUIRED_HEADERS, TraceHeaders
from text2sql_contracts.query import (
    ExecutionResult,
    QueryRequest,
    QueryResponse,
    QueryStatus,
    ResultPayload,
    User,
    UserRole,
)
from text2sql_contracts.state import (
    ExplanationResult,
    GraphState,
    NodeName,
    OpaDecision,
    OutputMaskResult,
    PiiAnalysis,
    PiiEntity,
    SchemaCard,
    SchemaLinkResult,
    Span,
    SqlValidationResult,
)

__all__ = [
    "ErrorCode",
    "ErrorPayload",
    "ExecutionResult",
    "ExplanationResult",
    "FailureMode",
    "FeedbackRating",
    "FeedbackRequest",
    "FeedbackResponse",
    "GraphState",
    "NodeError",
    "NodeName",
    "OpaDecision",
    "OutputMaskResult",
    "PiiAnalysis",
    "PiiEntity",
    "QueryRequest",
    "QueryResponse",
    "QueryStatus",
    "REQUIRED_HEADERS",
    "ResultPayload",
    "SchemaCard",
    "SchemaLinkResult",
    "Span",
    "SqlValidationResult",
    "TraceHeaders",
    "User",
    "UserRole",
]

CONTRACT_VERSION = "1.0"
