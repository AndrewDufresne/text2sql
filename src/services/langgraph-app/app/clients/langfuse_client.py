"""Langfuse SDK wrapper. Best-effort; failures must NEVER break the request."""

from __future__ import annotations

from typing import Any

from langfuse import Langfuse

from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)
_client: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    global _client
    if _client is not None:
        return _client
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        _log.warning("langfuse_disabled_no_keys")
        return None
    try:
        _client = Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
    except Exception as e:  # noqa: BLE001
        _log.warning("langfuse_init_failed", error=str(e))
        return None
    return _client


def emit_trace(*, trace_id: str, name: str, user_id: str, payload: dict[str, Any]) -> None:
    """Emit one trace to Langfuse.

    Targets the Langfuse Python SDK v2.x API (``client.trace(...)``), which is
    the wire-compatible series for the self-hosted ``langfuse/langfuse:2``
    server we run in Phase 1. SDK >= 3.x is OTel-based and breaks against the
    v2 server (project schema mismatch), so the package is pinned in pyproject.
    """
    lf = get_langfuse()
    if lf is None:
        return
    try:
        lf.trace(id=trace_id, name=name, user_id=user_id, metadata=payload)
        lf.flush()
    except Exception as e:  # noqa: BLE001
        _log.warning("langfuse_emit_failed", error=str(e))
