# ADR-0006: Phase 4 — Observability + Operability (LGTM + OTel + Portainer)

Date: 2026-05-05
Status: Accepted

## Context

Phases 1-3 delivered the walking skeleton (LangGraph + LiteLLM + Trino + Cube
+ DataHub-light), Phase 2 added RAG + safety, and Phase 3 wired HITL feedback
+ a Promptfoo-style golden-set evaluator. The platform is now usable and
governed, but we have *no in-house pane of glass*: Langfuse covers prompt
traces, but cross-service latency, security blocks, self-repair pressure,
infra health, and structured logs all required SSH-into-container debugging.

The Architecture (§9, L0/L1) commits to a Grafana LGTM stack + Portainer for
container ops. This ADR formalises the Phase 4 slice that closes the gap.

## Decision

Add a **Phase 4 observability slice** scoped to the local Docker Compose
deployment, deliverables:

1. **First-party metrics**. `langgraph-app` exposes `GET /metrics` (Prometheus
   exposition) with the canonical `text2sql_*` series defined in
   `app/metrics.py`:
   - `text2sql_requests_total{status,error_code}`
   - `text2sql_request_latency_seconds_bucket` (histogram)
   - `text2sql_security_blocks_total{reason}`  ← PII / Injection / SQL_UNSAFE / OPA_DENIED
   - `text2sql_self_repair_total`
   - `text2sql_llm_calls_total{purpose,outcome}`
   - `text2sql_feedback_total{sink,rating}`

2. **OTel auto-instrumentation** on FastAPI. Best-effort: when
   `OTEL_EXPORTER_OTLP_ENDPOINT` is unset (unit tests, venv runs),
   `configure_otel()` is a no-op. In containers, traces flow via OTLP HTTP →
   `otel-collector` → Tempo.

3. **Compose layer 70-observability.yml**: prometheus + alertmanager + loki +
   tempo + otel-collector + grafana (single-binary Loki/Tempo "monolithic"
   mode; storage on named volumes; 30d Prom retention, 7d trace retention).

4. **Compose layer 80-portal.yml**: portainer-ce. Backstage is *deferred*
   (heavy Node build for marginal Phase-4 value; revisit when service count
   doubles).

5. **Configs**: `config/{prometheus,grafana,loki,tempo,alertmanager,otel-collector}/`
   with Grafana auto-provisioned datasources (Prom default, Loki, Tempo) and
   one starter dashboard `t2sql/ai`.

6. **Make targets**: `up-obs`, `down-obs`, `up-portal`, `up-all`, `health-obs`.

7. **Tests**: 4 new unit tests in `tests/unit/test_metrics.py` exercise
   `/metrics`, the request counter, the security-block counter, and the
   feedback counter. No new external dependencies in unit tests (TestClient
   only).

## Consequences

### Positive
- Single dashboard URL gives ops + AI team a real-time view of the SLO panel
  defined in L0 §4 (latency, OK rate, security blocks, self-repair pressure).
- Tempo gives `service.name=langgraph-app` request-level traces — already
  validated in development.
- `text2sql_security_blocks_total` gives Compliance an auditable counter for
  guardrail effectiveness.
- Stack additions are idempotent: running only `up-obs` does not require the
  app stack; running `up-all` brings everything up coherently.

### Negative / Trade-offs
- **No structured-log shipping in this slice.** Loki is deployed but
  langgraph-app currently writes JSON to stdout — Loki ingest from container
  stdout requires either Promtail or the Docker `loki` log driver. We chose
  to ship the OTel SDK first because it gives both traces and (eventually)
  logs through one path; Promtail is a Phase 4.1 follow-up.
- **Backstage deferred.** The L0 doc still lists it; we mark it explicitly
  as out-of-scope here.
- **Alertmanager has no upstream receiver.** Routes go to a `dev-null`
  receiver; production must override with Slack/Teams/Email webhooks.

### Roll-back
`make down-obs` + `make down-portal` removes everything Phase 4 added; the
app continues to run (the metrics endpoint stays live, OTel SDK no-ops once
the collector is gone).

## Alternatives considered

- **Use Langfuse alone for traces.** Already in use, but Langfuse is
  prompt-centric — it lacks infra metrics and cross-service spans. Keep both.
- **Push metrics via OTLP instead of `/metrics` scrape.** OTel metrics SDK
  is heavier and pull-based scrape is the operational standard for
  Prometheus; we kept the SDK for traces only.
- **Single-binary Grafana Agent / Alloy.** Newer, but Loki + Promtail +
  OTel Collector is more documented and matches the L0 component list.
