"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from text2sql_contracts import (
    FeedbackRequest,
    FeedbackResponse,
    QueryRequest,
    QueryResponse,
)

from app.capability import CAPABILITIES, EXAMPLES, GLOSSARY
from app.clients import argilla_client, chat_store, pgvector_store
from app.graph import run_query
from app.metrics import FEEDBACK_TOTAL, configure_otel, render_latest
from app.observability import configure_logging, get_logger
from app.settings import get_settings

_settings = get_settings()
configure_logging(_settings.log_level)
_log = get_logger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Best-effort schema-card seed; degrades gracefully if pgvector / TEI down.
    if _settings.schema_link_enabled:
        try:
            await pgvector_store.ensure_index_seeded()
        except Exception as e:  # noqa: BLE001
            _log.warning("startup_schema_seed_failed", error=str(e))
    yield
    try:
        await pgvector_store.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        await chat_store.close()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(
    title="cib-text2sql-assistant",
    version=_settings.app_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=_lifespan,
)

# CORS — the Next.js web-ui runs on a different host port. Tightened in prod
# via WEB_UI_PUBLIC_BASE_URL once a real reverse proxy is in front.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Best-effort OTel auto-instrumentation. No-op without OTLP endpoint.
configure_otel(app, service_name="langgraph-app", service_version=_settings.app_version)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": _settings.app_version}


@app.get("/metrics")
async def metrics() -> Response:
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


# --------------------------------------------------------------- /query ------
@app.post("/api/v1/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    _log.info(
        "query_received",
        trace_id=str(req.trace_id),
        user_id=req.user.id,
        question_chars=len(req.question),
    )
    try:
        return await run_query(req)
    except Exception as e:  # noqa: BLE001
        _log.exception("query_unhandled_error", trace_id=str(req.trace_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/v1/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest) -> FeedbackResponse:
    """HITL feedback sink (200 unless request itself is malformed)."""
    _log.info(
        "feedback_received",
        trace_id=req.trace_id,
        user_id=req.user_id,
        rating=req.rating.value,
    )
    try:
        accepted, sink, record_id, detail = await argilla_client.submit(req)
    except Exception as e:  # noqa: BLE001
        _log.exception("feedback_unhandled_error", trace_id=req.trace_id)
        FEEDBACK_TOTAL.labels(sink="dropped", rating=req.rating.value).inc()
        raise HTTPException(status_code=500, detail=str(e)) from e
    FEEDBACK_TOTAL.labels(sink=sink or "unknown", rating=req.rating.value).inc()
    return FeedbackResponse(
        accepted=accepted, record_id=record_id, sink=sink, detail=detail
    )


# ---------------------------------------------- capability self-description --
@app.get("/api/v1/capabilities")
async def capabilities() -> dict[str, Any]:
    """Static + runtime capability surface for the UI capability panel."""
    return {
        **CAPABILITIES,
        "version": _settings.app_version,
        "limits": {
            **CAPABILITIES["limits"],
            "row_limit_default": _settings.row_limit_default,
            "row_limit_hard_max": _settings.row_limit_hard_max,
            "self_repair_max": _settings.self_repair_max,
            "llm_timeout_s": _settings.llm_timeout_s,
        },
    }


@app.get("/api/v1/glossary")
async def glossary(
    q: str | None = Query(default=None, description="prefix filter"),
) -> dict[str, Any]:
    """Curated business-term glossary the assistant understands."""
    items = GLOSSARY
    if q:
        needle = q.lower().strip()
        items = [g for g in GLOSSARY if needle in g["term"].lower()]
    return {"count": len(items), "items": items}


@app.get("/api/v1/examples")
async def examples() -> dict[str, Any]:
    """Curated example questions for the empty state."""
    return {"count": len(EXAMPLES), "items": EXAMPLES}


# -------------------------------------------------------- chat persistence ---
class ThreadCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=240)
    user_id: str = Field(..., min_length=1, max_length=120)


class ThreadRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=240)


class MessageAppend(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    query_id: UUID | None = None
    payload: dict[str, Any] | None = None


@app.get("/api/v1/threads")
async def list_threads(user_id: str = Query(..., min_length=1)) -> dict[str, Any]:
    items = await chat_store.list_threads(user_id)
    return {"count": len(items), "items": items}


@app.post("/api/v1/threads", status_code=201)
async def create_thread(body: ThreadCreate) -> dict[str, Any]:
    return await chat_store.create_thread(body.user_id, body.title)


@app.get("/api/v1/threads/{thread_id}")
async def get_thread(thread_id: UUID, user_id: str = Query(...)) -> dict[str, Any]:
    t = await chat_store.get_thread(thread_id, user_id)
    if not t:
        raise HTTPException(status_code=404, detail="thread not found")
    return t


@app.patch("/api/v1/threads/{thread_id}")
async def patch_thread(
    thread_id: UUID, body: ThreadRename, user_id: str = Query(...)
) -> dict[str, str]:
    ok = await chat_store.rename_thread(thread_id, user_id, body.title)
    if not ok:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"status": "ok"}


@app.delete("/api/v1/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: UUID, user_id: str = Query(...)) -> Response:
    ok = await chat_store.delete_thread(thread_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="thread not found")
    return Response(status_code=204)


@app.get("/api/v1/threads/{thread_id}/messages")
async def list_messages(
    thread_id: UUID, user_id: str = Query(...)
) -> dict[str, Any]:
    items = await chat_store.list_messages(thread_id, user_id)
    if items is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"count": len(items), "items": items}


@app.post("/api/v1/threads/{thread_id}/messages", status_code=201)
async def append_message(
    thread_id: UUID, body: MessageAppend, user_id: str = Query(...)
) -> dict[str, Any]:
    # Confirm ownership before insert.
    t = await chat_store.get_thread(thread_id, user_id)
    if not t:
        raise HTTPException(status_code=404, detail="thread not found")
    return await chat_store.append_message(
        thread_id=thread_id,
        role=body.role,
        content=body.content,
        query_id=body.query_id,
        payload=body.payload,
    )


@app.exception_handler(Exception)
async def _unhandled(_request, exc: Exception) -> JSONResponse:  # type: ignore[no-untyped-def]
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL",
                "message": str(exc),
                "trace_id": str(uuid4()),
            }
        },
    )
