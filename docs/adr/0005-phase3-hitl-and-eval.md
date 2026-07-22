# ADR-0005: Phase 3 — HITL feedback + NL explanation + Golden-Set Eval

* Status: Accepted (2026-05-05)
* Phase: 3 (HITL + Eval) — see `docs/Architecture.md` §8
* Supersedes: nothing
* Related: ADR-0003 (walking skeleton), ADR-0004 (RAG + Security)

## Context

Phase 1 produced a walking skeleton. Phase 2 added a security perimeter
(PII / injection / OPA) and RAG schema-link. We are now ready to close the
human loop:

1. **Output safety** — Phase 2 only sanitizes inbound questions; outbound
   result rows and explanations could still leak PII obtained from the
   warehouse (e.g. an `email` column).
2. **NL explanation** — RM/Risk pilots report "I see SQL + a number, but
   I don't trust I asked the right question". A short business-language
   summary closes the trust gap and is also a natural surface for the
   thumbs-up/down feedback widget.
3. **Feedback → Golden Set** — without a feedback sink we have no path
   from "user correction" to "regression test" and the model silently
   drifts. Argilla is the lightest off-the-shelf option that ships its
   own UI for the data team to triage corrections.
4. **CI gate on quality** — Promptfoo / a Python harness must turn the
   Golden Set into a build-blocking check. Code-only PRs can otherwise
   silently regress prompt quality.

## Decision

Add **two nodes** + **one endpoint** + **one container** + **one CI gate**:

| Layer | Addition |
|---|---|
| L5 (graph) | `explain` node (non-blocking, after `execute`) |
| L5 (graph) | `output_mask` node (Presidio + offline fallback, after `explain`) |
| L4 (capability) | reuse existing Presidio + LiteLLM |
| L7 (API) | `POST /api/v1/feedback` accepting thumbs/correction |
| L6 (HITL) | `argilla/argilla-quickstart` container in `compose/60-hitl.yml` |
| L1 (eval) | `tests/eval/run_eval.py` + `golden_set.yaml`; CI workflow `eval` |

### Sink fallback

Argilla is a heavyweight quickstart image (~2GB, ~90s warm-up). To keep
the langgraph-app usable when Argilla is down, the feedback client
**always** falls back to appending JSONL on local disk rather than failing
the call. The response surface (`sink: argilla | local-jsonl`) tells the
caller which sink absorbed the record.

### Why a Python eval harness alongside Promptfoo

Promptfoo's strength is prompt diff'ing in a Node UI. Its weakness for
our pipeline is that our richest assertions (`tables_used`, `error_code`,
`row_count_min`) are easier to express in Python against our typed
contracts than in Promptfoo's plugin model. We ship both:

* `tests/eval/run_eval.py` — source of truth for CI, no Node dep.
* `tests/eval/promptfoo.yaml` — for analyst exploration only.

### Why `explain` is non-blocking

Failure modes for `explain` are dominated by network/LLM 5xx. Refusing
the whole answer because the post-hoc prose failed would be a worse user
experience than serving the SQL + rows with a missing summary. We record
`EXPLAIN_FAILED` to Langfuse so an SRE dashboard can spot regression.

### Why `output_mask` re-runs Presidio (rather than diff-checking)

Two reasons:
1. `pii_guard` only inspects the **question**, not the data warehouse.
2. The masked text **and** the redaction counters are needed in the trace
   for compliance review. A diff-only check would not produce that.

## Consequences

Positive:
* Feedback path closed. Every wrong answer becomes a Golden-Set candidate
  one click away.
* Regression-proof prompts: any prompt change must keep ≥ 90% of the
  Golden Set passing or the build is red.
* Output PII compliance — even if a malicious user crafts a question that
  passes input pii_guard but lures a PII-laden column into the result
  set, the row is masked before it leaves the API.

Negative / accepted:
* Two extra LiteLLM calls per OK query (explain + LiteLLM cost). Mitigated
  by a low `EXPLAIN_MAX_TOKENS` (180) and a `EXPLAIN_ENABLED=false`
  kill switch.
* Argilla quickstart ships its own Postgres + ES — heavy. Production
  swap to `argilla/argilla-server` + external state is deferred to P4.
* Golden-Set CI requires the live stack and so runs on `workflow_dispatch`
  in this phase rather than every PR.

## Out of scope (Phase 4)

* TEI reranker as a second LiteLLM call.
* DataHub ingest + Cube `/meta` introspection.
* SSO + per-user feedback attribution.
* Backstage developer portal.
