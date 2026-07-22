"""Phase 4 — Prometheus metrics + OpenTelemetry tracing.

Exposed at ``GET /metrics`` (text/plain Prometheus exposition format).

Metric naming follows the L0 convention ``text2sql_<area>_<metric>``.
All metrics are process-local; aggregation happens in Prometheus.

OpenTelemetry is configured lazily: when ``OTEL_EXPORTER_OTLP_ENDPOINT``
is unset (or import fails), tracing degrades to no-op so unit tests and
local runs without an OTel Collector keep working.
"""

from __future__ import annotations

import os
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

# A dedicated registry keeps test isolation simple (no global state leaks
# across pytest sessions) and avoids the default registry's stdlib metrics
# being scraped accidentally.
REGISTRY = CollectorRegistry()

REQUESTS_TOTAL = Counter(
    "text2sql_requests_total",
    "Total /api/v1/query requests by terminal status and error code.",
    labelnames=("status", "error_code"),
    registry=REGISTRY,
)

LATENCY_SECONDS = Histogram(
    "text2sql_request_latency_seconds",
    "End-to-end query latency (seconds), measured in graph.run_query.",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0),
    registry=REGISTRY,
)

SECURITY_BLOCKS_TOTAL = Counter(
    "text2sql_security_blocks_total",
    "Refused requests broken down by security reason.",
    labelnames=("reason",),  # PII_DETECTED | PROMPT_INJECTION | SQL_UNSAFE | OPA_DENIED
    registry=REGISTRY,
)

SELF_REPAIR_TOTAL = Counter(
    "text2sql_self_repair_total",
    "Number of times the sql_validate -> sql_generate self-repair edge fired.",
    registry=REGISTRY,
)

FEEDBACK_TOTAL = Counter(
    "text2sql_feedback_total",
    "Submitted /api/v1/feedback records by sink (argilla|local|dropped).",
    labelnames=("sink", "rating"),
    registry=REGISTRY,
)

LLM_CALLS_TOTAL = Counter(
    "text2sql_llm_calls_total",
    "LiteLLM completion calls by purpose (sql_generate|explain) and outcome.",
    labelnames=("purpose", "outcome"),  # outcome: ok|error
    registry=REGISTRY,
)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


# ------------------------------------------------------------------ OTel ----

_OTEL_CONFIGURED = False


def configure_otel(app: Any, *, service_name: str, service_version: str) -> None:
    """Best-effort OTel auto-instrumentation for FastAPI.

    No-op if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset — keeps unit tests
    and venv runs free of OTLP connection errors.
    """
    global _OTEL_CONFIGURED
    if _OTEL_CONFIGURED:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
            }
        )
        provider = TracerProvider(resource=resource)
        # OTLP HTTP path: collector listens on /v1/traces by default.
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        _OTEL_CONFIGURED = True
    except Exception:  # noqa: BLE001
        # Tracing is best-effort; never crash the API on observability errors.
        return
