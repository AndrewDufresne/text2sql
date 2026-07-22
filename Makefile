# Text2SQL Platform — Phase 1 Makefile
# Tested with GNU Make 4.x (Git Bash / WSL on Windows, or Make for Windows)

SHELL := /usr/bin/env bash
COMPOSE := docker compose --env-file .env

# Compose file groups
F_NET   := -f compose/00-network.yml
F_STATE := -f compose/10-state.yml
F_PLAT  := -f compose/20-platform.yml
F_DATA  := -f compose/30-data.yml
F_DH    := -f compose/31-datahub.yml
F_CAP   := -f compose/40-capability.yml
F_APP   := -f compose/50-app.yml
F_HITL  := -f compose/60-hitl.yml
F_OBS   := -f compose/70-observability.yml
F_PORTAL := -f compose/80-portal.yml

# Walking skeleton minimum stack (Phase 1 + Phase 2 capability layer)
F_MIN := $(F_NET) $(F_STATE) $(F_PLAT) $(F_DATA) $(F_CAP) $(F_APP)
# Phase 3 stack adds Argilla
F_HITL_FULL := $(F_MIN) $(F_HITL)
# Phase 4 stack: full app + obs + portal
F_FULL := $(F_HITL_FULL) $(F_OBS) $(F_PORTAL)

.PHONY: help up-min down-min logs ps health smoke-trino test test-unit test-e2e \
        format lint clean vendor up-hitl down-hitl eval test-e2e-phase2 test-e2e-phase3 \
        up-obs down-obs up-portal down-portal up-all down-all health-obs \
        up-cube down-cube up-datahub down-datahub datahub-ingest datahub-glossary health-l3 \
        argilla-bootstrap argilla-sync-golden

help:
	@echo "make up-min       # bring up Phase 1 walking-skeleton stack"
	@echo "make down-min     # tear down (keeps volumes)"
	@echo "make logs         # follow logs"
	@echo "make ps           # list containers"
	@echo "make health       # ping all services"
	@echo "make smoke-trino  # SELECT count(*) FROM cib.client"
	@echo "make test         # all tests"
	@echo "make test-unit    # unit + contract tests only"
	@echo "make test-e2e     # walking skeleton E2E (requires up-min)"

vendor:
	@for svc in langgraph-app; do \
	  rm -rf services/$$svc/vendor/text2sql-contracts; \
	  mkdir -p services/$$svc/vendor/text2sql-contracts; \
	  cp -r packages/contracts/. services/$$svc/vendor/text2sql-contracts/; \
	done
	@echo "[vendor] contracts copied"

up-min: vendor
	$(COMPOSE) $(F_MIN) up -d --build

down-min:
	$(COMPOSE) $(F_MIN) down

logs:
	$(COMPOSE) $(F_MIN) logs -f --tail=100

ps:
	$(COMPOSE) $(F_MIN) ps

health:
	@echo "[trino]"     && curl -fsS http://localhost:$${TRINO_PORT:-8081}/v1/info | head -c 200 && echo
	@echo "[litellm]"   && curl -fsS http://localhost:$${LITELLM_PORT:-4000}/health/liveliness && echo
	@echo "[langfuse]"  && curl -fsS http://localhost:$${LANGFUSE_PORT:-3000}/api/public/health && echo
	@echo "[langgraph]" && curl -fsS http://localhost:$${LANGGRAPH_PORT:-8080}/healthz && echo

smoke-trino:
	curl -s -X POST -H "X-Trino-User: alice@bank" \
	  -H "X-Trino-Catalog: cib" -H "X-Trino-Schema: public" \
	  --data 'SELECT count(*) FROM client' \
	  http://localhost:$${TRINO_PORT:-8081}/v1/statement | jq .

test: test-unit test-e2e

test-unit:
	cd src/services/langgraph-app && python -m pytest -m "not e2e" -v

test-e2e:
	python -m pytest tests/e2e -m walking_skeleton -v

test-e2e-phase2:
	python -m pytest tests/e2e -m phase2 -v

test-e2e-phase3:
	python -m pytest tests/e2e -m phase3 -v

up-hitl: vendor
	$(COMPOSE) $(F_HITL_FULL) up -d --build

down-hitl:
	$(COMPOSE) $(F_HITL_FULL) down

eval:
	python tests/eval/run_eval.py \
	  --base-url http://localhost:$${LANGGRAPH_PORT:-8080} \
	  --golden tests/eval/golden_set.yaml \
	  --report tests/eval/report.json

# ---- Phase 3.1 — Argilla schema bootstrap + Golden Set sync ----
argilla-bootstrap:
	python -m tools.argilla.bootstrap \
	  --url http://localhost:$${ARGILLA_PORT:-6900} \
	  --api-key $${ARGILLA_API_KEY:-owner.apikey} \
	  --workspace $${ARGILLA_WORKSPACE:-admin} \
	  --dataset $${ARGILLA_DATASET:-text2sql-feedback} \
	  --vector-dim $${EMBEDDING_DIM:-384}

argilla-sync-golden:
	python -m tools.argilla.sync_golden \
	  --url http://localhost:$${ARGILLA_PORT:-6900} \
	  --api-key $${ARGILLA_API_KEY:-owner.apikey} \
	  --workspace $${ARGILLA_WORKSPACE:-admin} \
	  --dataset $${ARGILLA_DATASET:-text2sql-feedback} \
	  --golden tests/eval/golden_set.yaml

# ---- Phase 4 ----
up-obs:
	$(COMPOSE) $(F_NET) $(F_OBS) up -d

down-obs:
	$(COMPOSE) $(F_NET) $(F_OBS) down

up-portal:
	$(COMPOSE) $(F_NET) $(F_PORTAL) up -d

down-portal:
	$(COMPOSE) $(F_NET) $(F_PORTAL) down

up-all: vendor
	$(COMPOSE) $(F_FULL) up -d --build

down-all:
	$(COMPOSE) $(F_FULL) down

health-obs:
	@echo "[prometheus]"   && curl -fsS http://localhost:$${PROMETHEUS_PORT:-9090}/-/ready && echo
	@echo "[alertmanager]" && curl -fsS http://localhost:$${ALERTMANAGER_PORT:-9093}/-/ready && echo
	@echo "[loki]"         && curl -fsS http://localhost:$${LOKI_PORT:-3100}/ready && echo
	@echo "[tempo]"        && curl -fsS http://localhost:$${TEMPO_PORT:-3200}/ready && echo
	@echo "[grafana]"      && curl -fsS http://localhost:$${GRAFANA_PORT:-3001}/api/health && echo
	@echo "[langgraph /metrics]" && curl -fsS http://localhost:$${LANGGRAPH_PORT:-8080}/metrics | head -3

format:
	ruff format services packages tests

lint:
	ruff check services packages tests

clean:
	$(COMPOSE) $(F_MIN) down -v

# ---- L3 Knowledge layer UIs ----
# Cube ships with the data layer (30-data.yml). `up-cube` is the convenience
# target that brings up only postgres-cib + cube (no full app stack required).
up-cube:
	$(COMPOSE) $(F_NET) $(F_STATE) $(F_DATA) up -d cube

down-cube:
	$(COMPOSE) $(F_NET) $(F_DATA) stop cube && $(COMPOSE) $(F_NET) $(F_DATA) rm -f cube

# DataHub stack is independent (separate compose file). Heavy: ~4GB RAM, ~3min warm-up.
up-datahub:
	$(COMPOSE) $(F_NET) $(F_DH) up -d

down-datahub:
	$(COMPOSE) $(F_NET) $(F_DH) down

# Run a one-shot ingestion job that crawls postgres-cib into DataHub.
# Uses the official ingestion image so users don't need to pip-install locally.
datahub-ingest:
	docker run --rm --network t2sql-net --env-file .env \
	  -v $(PWD)/config/datahub:/config/datahub:ro \
	  acryldata/datahub-ingestion:v0.13.3 \
	  ingest -c /config/datahub/recipes/postgres-cib.yml

datahub-glossary:
	docker run --rm --network t2sql-net --env-file .env \
	  -v $(PWD)/config/datahub:/config/datahub:ro \
	  acryldata/datahub-ingestion:v0.13.3 \
	  ingest -c /config/datahub/recipes/glossary.yml

datahub-ingest-trino:
	docker run --rm --network t2sql-net --env-file .env \
	  -v $(PWD)/config/datahub:/config/datahub:ro \
	  acryldata/datahub-ingestion:v0.13.3 \
	  ingest -c /config/datahub/recipes/trino.yml

datahub-ingest-all: datahub-ingest datahub-glossary datahub-ingest-trino

health-l3:
	@echo "[cube]"     && curl -fsS http://localhost:$${CUBE_PORT:-4040}/readyz && echo
	@echo "[dh-gms]"   && curl -fsS http://localhost:$${DATAHUB_GMS_PORT:-8090}/health && echo
	@echo "[dh-front]" && curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:$${DATAHUB_FRONTEND_PORT:-9002}/admin
