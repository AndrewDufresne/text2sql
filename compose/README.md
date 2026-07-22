# Compose layout

| File | Stack | Purpose |
|---|---|---|
| `00-network.yml` | **default** | Shared bridge network `t2sql-net`. Up first. |
| `10-state.yml` | **default** | Postgres (platform metadata) + Postgres+pgvector (CIB seed). |
| `20-platform.yml` | **default** | LiteLLM → DeepSeek API + Langfuse. |
| `30-data.yml` | **default** | Trino query engine. |
| `40-capability.yml` | **default** | Presidio (PII) + TEI (embeddings) + OPA (authz). |
| `50-app.yml` | **default** | langgraph-app (FastAPI) + web-ui (Next.js). |
| `31-datahub.yml` | optional | DataHub catalog/glossary. NOT wired into pipeline. |
| `60-hitl.yml` | optional | Argilla HITL feedback. Disabled by default in app. |
| `70-observability.yml` | optional | Prom/Grafana/Loki/Tempo/OTel. |
| `80-portal.yml` | optional | Portainer container management. |

## Default stack (walking skeleton)

```powershell
docker compose --env-file .env `
  -f compose/00-network.yml `
  -f compose/10-state.yml `
  -f compose/20-platform.yml `
  -f compose/30-data.yml `
  -f compose/40-capability.yml `
  -f compose/50-app.yml `
  up -d
```

Or simply `make up-min`.

## First-run checklist

1. `make up-min` — wait for all healthchecks green (`make ps`)
2. `make smoke-trino` — confirms `client` table seeded
3. Open http://localhost:3203 (Web UI, primary) and ask: *"How many active clients are there?"*
4. Open http://localhost:3202 (Langfuse, login `admin@t2sql.local` / `admin_dev_only`)
5. Confirm a trace appears in Langfuse with `text2sql.query` name
