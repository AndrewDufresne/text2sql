# Changelog

All notable user-visible changes. SemVer; pre-1.0 minor bumps may be breaking.

## v1.0.0-rc1 — *Productisation* (current)

### Added
- New web UI built on **Next.js 15 + assistant-ui** (`services/web-ui`).
  Replaces Chainlit as the primary end-user interface.
- Server-side **chat history** (postgres-backed `chat_thread` /
  `chat_message`).
- **Capability panel**: glossary terms, allow-listed tables and example
  questions surfaced in the UI sidebar.
- New REST endpoints: `GET /api/v1/glossary`, `GET /api/v1/capabilities`,
  `GET /api/v1/examples`, `GET|POST /api/v1/threads`.
- **Air-gapped Ubuntu deployment** scripts (`scripts/server-{up,down,restart}.sh`)
  and image-transfer helpers.

### Changed
- Renamed user-facing surfaces from milestone codes ("Phase 1/2/3/4") to
  SemVer + product name. See [NAMING.md](./NAMING.md).
- `APP_VERSION` env: `phase4-observability` → `1.0.0-rc1`.
- Prompt versions: `sql_generate@phase2-v1` → `sql_generate@v1`,
  `explain@phase3-v1` → `explain@v1`.
- Presidio analyzer/anonymizer healthchecks: `start_period: 60s`,
  `timeout: 25s` (was timing out on cold gunicorn worker).
- Trino pinned to `442` (last release that supports x86-64-v2 / Ivy Bridge).

### Documentation
- Added [NAMING.md](./NAMING.md), this changelog and
  `docs/milestones/m1..m6.md` (PHASE\*.md moved + renamed).

---

## v0.5 — *Domain expansion* (M5)

- 13-table CIB warehouse (~75k rows): `client`, `account`, `exposure`,
  `transaction`, `daily_balance`, `covenant`, `collateral`, `kyc_event`,
  `trade_event`, `country_ref`, `industry_ref`, `fx_rate`, `risk_rating_history`.
- Cube schema with views and pre-aggregations.
- DataHub business glossary (~30 terms) and Trino → Cube lineage recipes.
- Golden Set expanded to 37 cases; eval pass rate 73% baseline.

## v0.4 — *Observability* (M4)

- Full OTel pipeline: Prometheus + Grafana + Loki + Tempo + Alertmanager.
- `text2sql_*` metric series in `/metrics`.
- Portainer for compose visibility.

## v0.3 — *HITL & Eval* (M3)

- Argilla feedback sink with local JSONL fallback.
- Golden Set + Promptfoo eval harness.
- Output PII mask (post-execute) and NL explanation.

## v0.2 — *Capabilities* (M2)

- Presidio PII guard, OPA authz, TEI + pgvector schema-link.
- One-shot self-repair on validation failure.

## v0.1 — *Walking skeleton* (M1)

- LiteLLM + Langfuse + Trino + LangGraph + Chainlit, end-to-end.
