#!/usr/bin/env bash
# server-restart.sh — restart the stack on the Ubuntu host.
#
# Usage:  bash scripts/server-restart.sh                       # restart all services in place (fast)
#         bash scripts/server-restart.sh --recreate            # down + up (picks up compose changes)
#         bash scripts/server-restart.sh svc1 svc2 ...         # restart specific services only
#         bash scripts/server-restart.sh --recreate svc1 svc2  # force-recreate specific services
set -euo pipefail

cd "$(dirname "$0")/.."
export COMPOSE_PROJECT_NAME=t2sql

ENV_FILE=".env"
[[ -f "$ENV_FILE" ]] || { echo "ERROR: $ENV_FILE missing."; exit 1; }

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

recreate=0
if [[ "${1:-}" == "--recreate" ]]; then
  recreate=1
  shift
fi

# Remaining args = optional service list
services=("$@")

# Strip leftover t2sql-* containers compose doesn't track — prevents
# 'container name already in use' on full recreate.
clean_strays() {
  mapfile -t strays < <(docker ps -a --format '{{.Names}}' | grep -E '^t2sql-' || true)
  (( ${#strays[@]} )) || return 0
  tracked=$("${COMPOSE[@]}" ps -a --format '{{.Name}}' 2>/dev/null || true)
  for c in "${strays[@]}"; do
    if ! grep -qx "$c" <<<"$tracked"; then
      echo "[clean] removing stray: $c"
      docker rm -f "$c" >/dev/null || true
    fi
  done
}

if (( recreate )); then
  if (( ${#services[@]} )); then
    for s in "${services[@]}"; do
      docker rm -f "t2sql-${s#t2sql-}" 2>/dev/null || true
    done
    "${COMPOSE[@]}" up -d --force-recreate --no-deps "${services[@]}"
    echo "[ok] recreated: ${services[*]}"
  else
    "${COMPOSE[@]}" down
    clean_strays
    "${COMPOSE[@]}" up -d
    echo "[ok] full stack recreated."
  fi
else
  if (( ${#services[@]} )); then
    "${COMPOSE[@]}" restart "${services[@]}"
    echo "[ok] restarted: ${services[*]}"
  else
    "${COMPOSE[@]}" restart
    echo "[ok] all services restarted."
  fi
fi

echo
"${COMPOSE[@]}" ps --format 'table {{.Name}}\t{{.Status}}' | head -40
