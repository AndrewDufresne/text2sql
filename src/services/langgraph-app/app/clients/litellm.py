"""LiteLLM client (OpenAI-compatible). All LLM calls flow through here.

Per io-contracts §C4: every request carries `metadata.trace_id` so LiteLLM's
Langfuse callback links generations to the parent trace.
"""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.metrics import LLM_CALLS_TOTAL
from app.settings import get_settings


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        s = get_settings()
        _client = AsyncOpenAI(
            base_url=s.litellm_base_url + "/v1",
            api_key=s.litellm_api_key,
            timeout=s.llm_timeout_s,
            # Fail fast: a single LLM hang must not multiply the user's wait
            # time by 3 via implicit OpenAI SDK retries. Higher-level retry
            # policy (sql self-repair) lives in the LangGraph runner.
            max_retries=0,
        )
    return _client


async def generate_sql(
    *,
    system_prompt: str,
    user_prompt: str,
    trace_id: str,
    user_id: str,
    session_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Returns (raw_text, metadata). Caller is responsible for extracting SQL."""
    s = get_settings()
    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=s.litellm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            # OpenAI-compatible "extra_body" carries LiteLLM metadata
            extra_body={
                "metadata": {
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "generation_name": "sql_generate",
                    "tags": ["text2sql", "phase1"],
                }
            },
        )
    except Exception:
        LLM_CALLS_TOTAL.labels(purpose="sql_generate", outcome="error").inc()
        raise
    LLM_CALLS_TOTAL.labels(purpose="sql_generate", outcome="ok").inc()
    text = (resp.choices[0].message.content or "").strip()
    meta = {
        "model": resp.model,
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
        "completion_tokens": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
        "raw_response": json.loads(resp.model_dump_json()),
    }
    return text, meta


async def generate_explanation(
    *,
    system_prompt: str,
    user_prompt: str,
    trace_id: str,
    user_id: str,
    session_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Phase 3 — short NL explanation of an answer. Same gateway, distinct
    `generation_name` so cost/latency lights up separately in Langfuse.
    """
    s = get_settings()
    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=s.litellm_explain_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=s.explain_max_tokens,
            extra_body={
                "metadata": {
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "generation_name": "explain",
                    "tags": ["text2sql", "phase3", "explain"],
                }
            },
        )
    except Exception:
        LLM_CALLS_TOTAL.labels(purpose="explain", outcome="error").inc()
        raise
    LLM_CALLS_TOTAL.labels(purpose="explain", outcome="ok").inc()
    text = (resp.choices[0].message.content or "").strip()
    meta = {
        "model": resp.model,
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
        "completion_tokens": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
    }
    return text, meta
