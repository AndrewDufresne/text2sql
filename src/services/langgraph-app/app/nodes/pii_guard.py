"""Node — pii_guard.

Two responsibilities, one node:
  1. Detect PII in the user's question (Presidio analyzer + offline fallback).
     If found, refuse early — no PII should ever reach the LLM.
  2. Detect prompt-injection signals (rule-based; cheap, deterministic).
     Treated as a refusal — never silently scrub instructions.

Output is attached to `state.pii`. The graph router refuses on either signal.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from text2sql_contracts import GraphState, NodeError, NodeName, PiiAnalysis, PiiEntity
from text2sql_contracts.errors import ErrorCode

from app.clients.presidio_client import analyze, anonymize
from app.observability import get_logger

_log = get_logger(__name__)

# Subset of Presidio entity types that we treat as actionable PII for a
# Text-to-SQL question. Categories like LOCATION / DATE_TIME / NRP /
# ORGANIZATION / URL are routinely legitimate business terms in queries
# (e.g. "USD by industry") and would otherwise produce false refusals.
_PII_BLOCK_TYPES: frozenset[str] = frozenset({
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_SSN",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "US_BANK_NUMBER",
    "PERSON",
    "IP_ADDRESS",
    "MEDICAL_LICENSE",
})

# Conservative phrase-list. Each one alone is suspicious in a SQL request.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_previous", re.compile(r"\bignore\s+(all\s+|the\s+)?(previous|above|prior)\b", re.I)),
    ("system_override", re.compile(r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\b", re.I)),
    ("reveal_prompt",  re.compile(r"\b(reveal|show|print|leak)\b.*\b(system|prompt|instructions?)\b", re.I)),
    ("ddl_in_text",    re.compile(r"\b(drop|truncate|delete|update|insert|alter|grant)\s+(table|from|into|database|schema)\b", re.I)),
    ("comment_smuggling", re.compile(r"--\s*(\bignore\b|\bsystem\b|\boverride\b)", re.I)),
    ("role_jailbreak", re.compile(r"\b(developer\s+mode|jailbreak|DAN|do\s+anything\s+now)\b", re.I)),
]


def detect_injection(text: str) -> list[str]:
    return [name for name, pat in _INJECTION_PATTERNS if pat.search(text)]


async def run(state: GraphState) -> GraphState:
    span = state.start_span(NodeName.PII_GUARD)
    started = span.started_at
    text = state.request.question
    try:
        hits = await analyze(text)
        # Filter to entity types we actually treat as blocking PII (avoid false
        # positives from LOCATION / DATE_TIME / ORGANIZATION on business terms).
        hits = [h for h in hits if h.get("entity_type") in _PII_BLOCK_TYPES]
        entities = [
            PiiEntity(
                entity_type=h.get("entity_type", "UNKNOWN"),
                start=int(h.get("start", 0)),
                end=int(h.get("end", 0)),
                score=float(h.get("score", 0.0)),
            )
            for h in hits
        ]
        sanitized = await anonymize(text, hits) if hits else None
        signals = detect_injection(text)

        # When PII is detected and sanitized, feed the sanitized text into
        # downstream nodes so legitimate queries mentioning real names are
        # not wrongly refused.
        if sanitized:
            state.request.question = sanitized

        state.pii = PiiAnalysis(
            has_pii=bool(entities),
            entities=entities,
            sanitized_text=sanitized,
            injection_suspected=bool(signals),
            injection_signals=signals,
        )
        span.attrs["pii_count"] = len(entities)
        span.attrs["injection_signals"] = signals

        if entities:
            span.status = "error"
            state.errors.append(
                NodeError(
                    node=NodeName.PII_GUARD.value,
                    code=ErrorCode.PII_DETECTED,
                    message=f"PII detected: {sorted({e.entity_type for e in entities})}",
                    details={"entities": [e.model_dump() for e in entities]},
                )
            )
        elif signals:
            span.status = "error"
            state.errors.append(
                NodeError(
                    node=NodeName.PII_GUARD.value,
                    code=ErrorCode.PROMPT_INJECTION,
                    message=f"Prompt-injection signals: {signals}",
                    details={"signals": signals},
                )
            )
        _log.info(
            "pii_guard_done",
            trace_id=str(state.trace_id),
            pii=len(entities),
            injection=signals,
        )
    finally:
        span.ended_at = datetime.now(timezone.utc)
        span.elapsed_ms = int((span.ended_at - started).total_seconds() * 1000)
    return state
