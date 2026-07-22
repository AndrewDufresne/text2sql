"""Presidio analyzer + anonymizer client.

We talk HTTP directly (not the Python SDK) — keeps the langgraph-app image
free of presidio's heavy NLP deps. Two endpoints:

  POST {analyzer}/analyze   -> [{entity_type, start, end, score, ...}]
  POST {anonymizer}/anonymize -> {text: "...", items: [...]}

If the service is unreachable we fall back to a tiny regex-based detector so
the pipeline still refuses obvious PII offline (testable without the stack).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)

# Conservative offline fallback regexes (used only when Presidio is down or
# disabled). These are NOT a security boundary on their own — Presidio is.
_OFFLINE_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL_ADDRESS": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "PHONE_NUMBER": re.compile(r"\+?\d[\d\s\-().]{7,}\d"),
    "IBAN_CODE": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    "US_SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def _offline_detect(text: str, threshold: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for et, pat in _OFFLINE_PATTERNS.items():
        for m in pat.finditer(text):
            out.append(
                dict(entity_type=et, start=m.start(), end=m.end(), score=0.95)
            )
    return [h for h in out if h["score"] >= threshold]


async def analyze(text: str, *, language: str = "en") -> list[dict[str, Any]]:
    s = get_settings()
    if not s.pii_enabled:
        return []
    payload = {"text": text, "language": language}
    try:
        async with httpx.AsyncClient(timeout=5.0) as cx:
            r = await cx.post(f"{s.presidio_analyzer_url}/analyze", json=payload)
            r.raise_for_status()
            data = r.json()
            return [h for h in data if h.get("score", 0) >= s.pii_score_threshold]
    except Exception as e:  # noqa: BLE001
        _log.warning("presidio_analyze_offline_fallback", error=str(e))
        return _offline_detect(text, s.pii_score_threshold)


async def anonymize(text: str, hits: list[dict[str, Any]]) -> str:
    """Replace each hit with `<ENTITY_TYPE>`. Done locally — no second HTTP hop
    needed, and deterministic for tests."""
    if not hits:
        return text
    # Sort descending so index math is stable.
    spans = sorted(hits, key=lambda h: h["start"], reverse=True)
    out = text
    for h in spans:
        s_, e_, et = int(h["start"]), int(h["end"]), str(h["entity_type"])
        out = out[:s_] + f"<{et}>" + out[e_:]
    return out
