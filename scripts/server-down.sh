#!/usr/bin/env bash
# server-down.sh — stop the stack on the Ubuntu host.
# Volumes are preserved by default. Use --nuke to also drop volumes + network.
#
# Usage:  bash scripts/server-down.sh           # stop all (keep data)
#         bash scripts/server-down.sh --nuke    # stop + drop volumes + network
#         bash scripts/server-down.sh --stop    # just stop containers (don't remove)
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

# Remove any leftover t2sql-* containers that compose doesn't track (e.g. created
# under a different project name in a previous run). Otherwise `up` will fail with
# 'container name already in use'.
clean_strays() {
  mapfile -t strays < <(docker ps -a --format '{{.Names}}' | grep -E '^t2sql-' || true)
  (( ${#strays[@]} )) || return 0
  tracked=$("${COMPOSE[@]}" ps -a --format '{{.Name}}' 2>/dev/null || true)
  for c in "${strays[@]}"; do
    if ! grep -qx "$c" <<<"$tracked"; then
      echo "[clean] removing stray container: $c"
      docker rm -f "$c" >/dev/null || true
    fi
  done
}

mode="${1:-down}"
case "$mode" in
  down|"")
    "${COMPOSE[@]}" down
    clean_strays
    echo "[ok] stack down (volumes preserved)."
    ;;
  --stop|stop)
    "${COMPOSE[@]}" stop
    echo "[ok] containers stopped (not removed)."
    ;;
  --nuke|nuke)
    read -r -p "This will DELETE ALL volumes (postgres, datahub, grafana, …). Type 'NUKE' to confirm: " ans
    [[ "$ans" == "NUKE" ]] || { echo "aborted."; exit 1; }
    "${COMPOSE[@]}" down -v
    clean_strays
    docker network rm t2sql-net 2>/dev/null || true
    echo "[ok] stack + volumes + network removed."
    ;;
  *)
    echo "unknown: $mode  (down|stop|nuke)"; exit 2 ;;
esac
