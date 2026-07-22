# L3 Knowledge Layer — Cube + DataHub UIs

Two UIs go live with this slice:

| UI | URL | Default credentials | Warm-up |
|---|---|---|---|
| **Cube Playground** | http://localhost:4040 | none (dev mode) | ~15s |
| **DataHub Frontend** | http://localhost:9002 | `datahub` / `datahub` | ~3-5 min (first boot) |

---

## Cube — Semantic Layer

**What it gives you**: a controlled vocabulary of measures and dimensions
(`Client.active_count`, `Exposure.utilisation_pct`, …) that the LLM can
target instead of hand-rolling SQL against raw columns.

### Bring up
```cmd
make up-cube
make health-l3
```

### Maintain schemas
- Files live under [config/cube/schema/](../config/cube/schema/).
- Edit YAML → Cube hot-reloads in dev mode (no restart).
- `views/CustomerExposure.yml` is the recommended LLM entry point.

### Validate in the Playground
1. Open http://localhost:4040
2. **Build** tab → pick measure `Exposure.total_notional_usd`,
   dimension `Client.country` → **Run** → preview rows + generated SQL.
3. The SQL pane is the contract surface for what the LangGraph
   `schema_link` node should hand off in Phase 6.

---

## DataHub — Catalog + Glossary + Lineage

**What it gives you**: a self-service catalog where data Owners,
business analysts and Compliance can edit table descriptions, define
business terms, and tag PII columns — all without engineer involvement.

### Bring up
```cmd
make up-datahub
REM wait ~3-5 min for first-time init job (datahub-upgrade SystemUpdate)
make health-l3
make datahub-ingest        REM crawl postgres-cib tables into the catalog
make datahub-glossary      REM seed CIB business-glossary terms
```

### Resource budget
| Container | RAM | Disk |
|---|---|---|
| elasticsearch | ~1.5 GB | ~500 MB |
| kafka + zookeeper | ~700 MB | ~200 MB |
| mysql | ~400 MB | ~100 MB |
| datahub-gms | ~1 GB | — |
| datahub-frontend | ~500 MB | — |
| **Total** | **~4 GB** | **~1 GB** |

> If memory is tight, run `make down-datahub` between sessions —
> volumes persist, restart is faster (~90s).

### Day-to-day maintenance
| Task | Where | Who |
|---|---|---|
| Add column descriptions | DataHub UI → Dataset → Edit Documentation | Data Owner |
| Add business term | UI → Glossary → New Term | Business + Governance |
| Tag PII column | UI → Dataset → schema row → Add Tag | Compliance |
| Re-crawl source after schema change | `make datahub-ingest` | Data Engineer |
| Update Glossary in bulk | edit [glossary/business-glossary.yml](../config/datahub/glossary/business-glossary.yml) → `make datahub-glossary` | Governance |

### Phase 6 hooks (not yet wired)
- `loaders/cube_loader.py` will pull `/meta` from Cube into pgvector.
- `loaders/datahub_loader.py` will pull Glossary terms into pgvector
  so the LLM resolves "活跃客户" → `Client.active_count`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Cube `/readyz` 500 | Check `t2sql-cube` logs — most often a YAML parse error in `config/cube/schema/*.yml` |
| DataHub UI blank / "GMS not reachable" | `docker logs t2sql-dh-gms` — wait for `Started MetadataChangeProposalsProcessor`; ES needs ~60s before GMS becomes healthy |
| `datahub-upgrade` exits with non-zero | First run can race ES — `make down-datahub && make up-datahub` once ES is fully ready |
| Ingestion fails: `connection refused postgres-cib:5432` | Ensure `make up-min` (or at least `up-cube`) ran first so postgres-cib is on `t2sql-net` |
| Port 9002 already in use | Override `DATAHUB_FRONTEND_PORT` in `.env` |
