#!/usr/bin/env bash
# server-up.sh — one-shot bring-up on the Ubuntu host.
# Idempotent: safe to re-run.
#
# Usage:  bash scripts/server-up.sh           # bring up full stack
#         bash scripts/server-up.sh down      # tear down (keep volumes)
#         bash scripts/server-up.sh nuke      # tear down + drop volumes
#         bash scripts/server-up.sh status    # ps + health
set -euo pipefail

cd "$(dirname "$0")/.."
export COMPOSE_PROJECT_NAME=t2sql

ENV_FILE=".env"
[[ -f "$ENV_FILE" ]] || { echo "ERROR: $ENV_FILE missing — copy .env.server -> .env first."; exit 1; }

COMPOSE=(docker compose --env-file "$ENV_FILE"
  -f compose/00-network.yml
  -f compose/10-state.yml
  -f compose/20-platform.yml
  -f compose/30-data.yml
  -f compose/31-datahub.yml
  -f compose/40-capability.yml
  -f compose/50-app.yml
  -f compose/60-hitl.yml
  -f compose/70-observability.yml
  -f compose/80-portal.yml
)

vendor_contracts() {
  for svc in langgraph-app chainlit-ui; do
    dst="services/$svc/vendor/text2sql-contracts"
    rm -rf "$dst"; mkdir -p "$dst"
    cp -r src/packages/contracts/. "$dst/"
  done
  echo "[vendor] contracts copied"
}

ensure_network() {
  docker network inspect t2sql-net >/dev/null 2>&1 || docker network create t2sql-net
}

# Remove any t2sql-* containers that compose doesn't track (started manually
# with docker run, or under a different project name). These cause
# 'container name already in use' errors on `up`.
clean_strays() {
  mapfile -t all < <(docker ps -a --filter 'name=^t2sql-' --format '{{.Names}}' || true)
  (( ${#all[@]} )) || return 0
  tracked=$("${COMPOSE[@]}" ps -a --format '{{.Name}}' 2>/dev/null || true)
  for c in "${all[@]}"; do
    if ! grep -qx "$c" <<<"$tracked"; then
      echo "[clean] removing stray container: $c"
      docker rm -f "$c" >/dev/null || true
    fi
  done
}

cmd="${1:-up}"
case "$cmd" in
  up)
    ensure_network
    vendor_contracts
    clean_strays
    # NOTE: NO --build — we shipped pre-built images via deploy script.
    "${COMPOSE[@]}" up -d
    echo "[ok] stack up. Run: bash scripts/server-up.sh status"
    ;;
  down)
    "${COMPOSE[@]}" down
    clean_strays
    ;;
  nuke)
    "${COMPOSE[@]}" down -v
    clean_strays
    docker network rm t2sql-net 2>/dev/null || true
    ;;
  status)
    "${COMPOSE[@]}" ps
    echo
    set +e
    PORT=$(grep -E '^LANGGRAPH_PORT=' "$ENV_FILE" | cut -d= -f2)
    echo "[langgraph]  $(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:${PORT:-28080}/healthz)"
    PORT=$(grep -E '^CHAINLIT_PORT=' "$ENV_FILE" | cut -d= -f2)
    echo "[chainlit ]  $(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:${PORT:-28000}/)"
    PORT=$(grep -E '^GRAFANA_PORT=' "$ENV_FILE" | cut -d= -f2)
    echo "[grafana  ]  $(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:${PORT:-23001}/api/health)"
    PORT=$(grep -E '^DATAHUB_FRONTEND_PORT=' "$ENV_FILE" | cut -d= -f2)
    echo "[datahub  ]  $(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:${PORT:-29002}/)"
    ;;
  *)
    echo "unknown: $cmd  (up|down|nuke|status)"; exit 2 ;;
esac
