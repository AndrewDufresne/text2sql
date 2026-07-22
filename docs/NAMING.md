# Naming & Branding Conventions

Canonical names for the platform. **All user-visible text and new code must
follow this guide.** Existing internal identifiers (DB schema, container
prefixes, env vars) are kept as-is to avoid migration risk.

---

## 1. Brand

| Field | Value | Where it appears |
|---|---|---|
| Product name | **CIB Text-to-SQL Assistant** | Login page, docs, customer-facing |
| Internal codename | **Atlas** | Team channels, internal slides |
| Tagline | *Ask CIB data in plain language. Governed. Audited.* | Landing page hero |
| Vendor / owner | CIB Data Platform | Footer, About |
| Product version | `v1.0.0-rc1` (SemVer) | About dialog, `APP_VERSION` env |

> **Phase 1 / Phase 2 / Phase 3 / Phase 4 are internal milestones only.**
> They MUST NOT appear in any user-visible string. Use the SemVer version
> instead, and reference the changelog for what each release contains.

---

## 2. Service / repository identifiers (NOT renamed — internal only)

These are kept stable to avoid touching DB rows, env files, container names,
ingress, monitoring labels and ADR history. Treat them as opaque.

| Identifier | Status | Reason |
|---|---|---|
| Repo: `text2sql-platform` | keep | Git history; rename = breaks all clones |
| Container prefix: `t2sql-*` | keep | All compose project + Prometheus labels |
| DB schema: `cib.public.*` | keep | Trino + Cube + DataHub all reference |
| DB user: `t2sql` / `cib` | keep | Postgres role bound in many places |
| Env vars: `LANGGRAPH_PORT` etc. | keep | Industry-conventional naming |
| HTTP route: `/api/v1/query` | keep | Already clean |
| Service container_name: `t2sql-langgraph`, `t2sql-chainlit`, `t2sql-web-ui` | keep | |

---

## 3. Renamed (user-visible)

| Where | Old | New |
|---|---|---|
| Welcome banner | "CIB Text-to-SQL — Phase 4" | "CIB Text-to-SQL Assistant" |
| Chat author | `text2sql` | `Assistant` |
| `APP_VERSION` env | `phase4-observability` | `1.0.0-rc1` |
| Prompt version tag | `sql_generate@phase2-v1` | `sql_generate@v1` |
| Prompt version tag | `explain@phase3-v1` | `explain@v1` |
| Comment in `.env.example` | "Phase 1 environment template" | "Environment template" |
| `compose/*.yml` headers | "Phase X — ..." | "<service-area> — ..." |
| README sections | "Phase 1 walking skeleton stack" | "Quick start" |
| `docs/PHASE1.md` … `PHASE4.md` | (top-level) | `docs/milestones/m1-foundations.md` …
`m4-observability.md` |
| Pilot user banner in Chainlit | "Phase 4 — Walking skeleton + HITL + ..." | (removed; replaced by capability panel) |

---

## 4. Milestones (internal taxonomy — keep using in commits / PRs)

| Milestone | Theme | Released |
|---|---|---|
| M1 — Foundations | Walking skeleton (LiteLLM + Trino + LangGraph + Chainlit) | v0.1 |
| M2 — Capabilities | Presidio PII, OPA, TEI schema-link, self-repair | v0.2 |
| M3 — HITL & Eval | Argilla feedback, Golden Set, output mask, NL explain | v0.3 |
| M4 — Observability | OTel, Prom/Grafana/Loki/Tempo, Portainer | v0.4 |
| M5 — Domain Expansion | 13-table CIB warehouse, Cube views, DataHub glossary | v0.5 |
| M6 — Productisation | Air-gap deploy, web-ui, capability panel, naming cleanup | **v1.0.0-rc1 (current)** |

In commit messages prefer: `feat(m6): assistant-ui empty state + glossary @-mention`

---

## 5. Language policy

| Surface | Language |
|---|---|
| Code identifiers, log messages, comments | **English only** |
| User-visible UI strings | **English** (Chinese localisation deferred) |
| Architecture / ADR docs | **English** |
| Operations runbooks (`docs/runbooks/`) | English (Chinese cheat-sheets allowed under `docs/runbooks/zh/`) |
| Commit messages | English |

---

## 6. New names introduced in v1.0.0-rc1

| Concept | Name | Notes |
|---|---|---|
| Web UI service (Next.js + assistant-ui) | `web-ui` (container `t2sql-web-ui`) | Replaces Chainlit as primary UX |
| Legacy Chainlit | `chainlit-ui` (kept, container unchanged) | Still functional; mounted at `/legacy` |
| Glossary REST surface | `GET /api/v1/glossary` | DataHub proxy + cached |
| Capability self-description | `GET /api/v1/capabilities` | What the system can / cannot do |
| Curated example questions | `GET /api/v1/examples` | Empty-state hints |
| Chat persistence | `chat_thread`, `chat_message` (postgres-platform) | Server-side history |
