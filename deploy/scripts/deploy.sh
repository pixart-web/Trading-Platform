#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
MODE=${1:---dry-run}
export PA_ENV_FILE=${PA_ENV_FILE:-$ROOT_DIR/deploy/production.env}

"$ROOT_DIR/deploy/scripts/preflight.sh"
docker compose --env-file "$PA_ENV_FILE" -f "$ROOT_DIR/compose.production.yaml" build --pull api web migrate

if [ "$MODE" = "--dry-run" ]; then
  echo "Dry run complete. Re-run with --apply only after an approved deployment window."
  exit 0
fi
[ "$MODE" = "--apply" ] || { echo "Usage: $0 [--dry-run|--apply]" >&2; exit 2; }

"$ROOT_DIR/deploy/scripts/backup.sh"
docker compose --env-file "$PA_ENV_FILE" -f "$ROOT_DIR/compose.production.yaml" up -d --wait --wait-timeout 240
docker compose --env-file "$PA_ENV_FILE" -f "$ROOT_DIR/compose.production.yaml" ps
echo "Deployment started. Persistent mode remains authoritative; verify HTTPS, authentication, readiness and operator control before closing the window."
