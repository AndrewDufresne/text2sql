# ADR 0004 — Phase 2: RAG + Security

- **Status**: Accepted
- **Date**: 2026-05-05
- **Supersedes scope of**: ADR-0003 (extends, does not replace)

## Context

Phase 1 walking skeleton landed (single table `client`, 3-node linear pipeline,
sqlglot validation, DeepSeek via LiteLLM, Langfuse trace, Trino execution).

Phase 2 must add the **safety floor + retrieval brain** the architecture (§2.4)
mandates *before* any pilot user gets credentials:

1. **PII guard** — input scrubbing + output redaction (Presidio).
2. **OPA** — table × role authorisation as code, not in Python.
3. **pgvector + TEI** — schema-linking RAG so the LLM stops being told the
   whole catalog in the system prompt (it does not scale beyond a handful of
   tables).
4. **Self-repair** — single re-prompt on validation failure.
5. **Adopt `langgraph.StateGraph`** — branching now exists (validation fail →
   regenerate; pii fail → refuse; opa deny → refuse).

## Decision

### Scope IN
- Multi-table CIB schema: `client + account + exposure` (single transactions
  table is deferred — too many rows for vector demos and not needed for the
  acceptance queries below).
- New nodes (8 total): `pii_guard → schema_link → sql_generate ↔ sql_validate
  → opa_check → execute → emit`.
- Self-repair: max 1 retry (`SELF_REPAIR_MAX=1`) — Phase 3 may bump to 2.
- LangGraph `StateGraph` with conditional edges.
- Compose adds: `presidio-analyzer`, `presidio-anonymizer`, `tei-embed`,
  `opa`. **No** Argilla, **no** Cube, **no** DataHub yet (Phase 3 / 4).
- pgvector: schema-card collection seeded at app start (idempotent upsert),
  not in compose init — keeps DB seed pure SQL.

### Scope OUT (deferred)
- Cube `/meta` — Phase 3. Schema cards are hand-written for now (3 tables, OK).
- DataHub glossary — Phase 3.
- Reranker — Phase 3 (top-K=8 from embed-only is enough at this scale).
- Argilla / Promptfoo CI — Phase 3.
- Approval workflow — Phase 3.

### Acceptance bar
- Injection / unsafe-SQL test set: **100%** blocked (red-team `tests/security/`).
- Schema-link Recall@5 on a 30-question fixture ≥ 90%.
- Existing walking-skeleton question still answers correctly.
- All new nodes have unit tests (mock external deps).
- `make test-unit` green; `make up-min && make test-e2e` green with the new
  stack.

## Consequences

- ✅ Phase 2 stack runs entirely on CPU (TEI on CPU; `bge-m3` swapped for the
  smaller `bge-small-en-v1.5` to keep first-pull < 200 MB).
- ✅ OPA decisions are inspectable in Langfuse via the `opa_check` span.
- ⚠️ Adding TEI + Presidio adds ~3 GB to the compose footprint; acceptable on
  laptop but documented in PHASE2.md.
- ⚠️ Vendoring `text2sql-contracts` is still manual (Phase 1 quirk). Phase 3
  will switch to a proper monorepo tool — explicit non-goal here.
