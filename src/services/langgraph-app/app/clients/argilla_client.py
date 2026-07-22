"""Argilla feedback sink (Phase 3.1 — full L6 schema).

Two-tier sink (no feedback ever silently dropped):
  1. If `ARGILLA_ENABLED=true` and reachable, upsert via Argilla v2
     `/api/v1/datasets/by-name/{ws}/{ds}/records:bulk` (idempotent on `id`).
  2. Otherwise (or on any HTTP error) append a JSON line to
     `FEEDBACK_LOCAL_PATH` so a human can `cat | replay`.

Record schema follows `docs/layers/L6-hitl.md` §2.1:
  * `id`           = trace_id  (deterministic — enables Langfuse join +
                     idempotent upsert when the same user re-submits)
  * `fields`       = question / sql / corrected_sql / result_preview /
                     explanation / comment
  * `metadata`     = full set (rating / failure_mode / user / model /
                     prompt_version / cost / latency / tags / reviewed)
  * `vectors`      = {"question": question_embedding} (only if provided)
  * `responses`    = pre-filled SME response (rating + corrected_sql +
                     failure_mode); status="submitted" so it appears
                     immediately on the dashboard for review.

Defensive:
  * `corrected_sql` is parsed by sqlglot before write; if it doesn't
    parse we drop it (keeping the comment as the user's raw note) and
    add tag `corrected_sql_parse_error` so SMEs can still triage.  The
    *full* security check is re-run when (and if) the record is
    promoted to the Golden Set.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import sqlglot

from text2sql_contracts import FeedbackRating, FeedbackRequest

from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)


def _safe_corrected_sql(sql: str | None) -> tuple[str | None, str | None]:
    """Return (corrected_sql_or_none, parse_error_or_none)."""
    if not sql:
        return None, None
    try:
        stmts = sqlglot.parse(sql, read="trino")
        if not stmts or stmts[0] is None:
            return None, "empty_parse"
        return sql, None
    except Exception as e:  # noqa: BLE001
        return None, f"parse_error: {e}"


def _to_record(req: FeedbackRequest) -> dict[str, Any]:
    """Build an Argilla v2 record-shaped dict (without the top-level `id`)."""
    corrected, corrected_err = _safe_corrected_sql(req.corrected_sql)
    extra_tags = list(req.tags)
    if corrected_err is not None:
        extra_tags.append("corrected_sql_parse_error")

    fields = {
        "question": req.question,
        "sql": req.sql or "",
        "corrected_sql": corrected or "",
        "result_preview": req.result_preview or "",
        "explanation": req.explanation or "",
        "comment": req.comment or "",
    }

    metadata: dict[str, Any] = {
        "trace_id": req.trace_id,
        "user_id": req.user_id,
        "user_role": req.user_role,
        "business_unit": req.business_unit,
        "rating": req.rating.value,
        "failure_mode": req.failure_mode.value if req.failure_mode else None,
        "model": req.model,
        "prompt_version": req.prompt_version,
        "tables_used": req.tables_used,
        "metrics_used": req.metrics_used,
        "cost_usd": req.cost_usd,
        "latency_ms": req.latency_ms,
        "tags": extra_tags,
        "received_at": datetime.now(timezone.utc).isoformat(),
        # SME flips this to true after verifying corrected_sql; only then
        # does the sync_golden tool promote the record to the Golden Set.
        "reviewed": False,
    }
    if corrected_err is not None:
        metadata["corrected_sql_parse_error"] = corrected_err

    record: dict[str, Any] = {"fields": fields, "metadata": metadata}

    # Pre-fill the SME response form so the record lands on the dashboard
    # in a useful state instead of "empty draft".
    thumb_value = "up" if req.rating == FeedbackRating.THUMBS_UP else "down"
    response_values: dict[str, Any] = {"thumb": {"value": thumb_value}}
    if corrected:
        response_values["corrected_sql"] = {"value": corrected}
    if req.failure_mode:
        response_values["failure_mode"] = {"value": req.failure_mode.value}
    record["responses"] = [
        {
            "user_id": req.user_id,
            "status": "submitted",
            "values": response_values,
        }
    ]

    if req.question_embedding:
        record["vectors"] = {"question": list(req.question_embedding)}

    return record


def _append_local(req: FeedbackRequest, record_id: str) -> str:
    s = get_settings()
    path = s.feedback_local_path
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass
    line = json.dumps(
        {"record_id": record_id, **_to_record(req)},
        default=str,
        ensure_ascii=False,
    )
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


async def submit(req: FeedbackRequest) -> tuple[bool, str, str, dict[str, Any]]:
    """Returns (accepted, sink, record_id, detail).

    `record_id` == `trace_id` so callers can later locate the SME's
    review by trace and so a re-submit (e.g. user updates their
    correction) overwrites the previous record instead of duplicating.
    """
    s = get_settings()
    record_id = req.trace_id
    detail: dict[str, Any] = {}
    if s.argilla_enabled:
        url = (
            f"{s.argilla_url.rstrip('/')}"
            f"/api/v1/datasets/by-name/{s.argilla_workspace}/{s.argilla_dataset}/records:bulk"
        )
        payload = {"items": [_to_record(req) | {"id": record_id}]}
        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                headers={
                    "X-Argilla-Api-Key": s.argilla_api_key,
                    "Content-Type": "application/json",
                },
            ) as cx:
                r = await cx.post(url, json=payload)
                if r.status_code in (200, 201, 204):
                    return True, "argilla", record_id, {"status": r.status_code}
                detail["argilla_status"] = r.status_code
                detail["argilla_body"] = r.text[:500]
                _log.warning(
                    "argilla_post_failed_falling_back_local",
                    status=r.status_code,
                    body=r.text[:300],
                )
        except Exception as e:  # noqa: BLE001
            detail["argilla_error"] = str(e)
            _log.warning("argilla_unreachable_falling_back_local", error=str(e))
    path = _append_local(req, record_id)
    detail["local_path"] = path
    return True, "local-jsonl", record_id, detail
