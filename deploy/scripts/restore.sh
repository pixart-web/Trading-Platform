#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
DUMP=${1:-}
CONFIRM=${2:-}
[ -f "$DUMP" ] && [ -s "$DUMP" ] || { echo "Usage: $0 BACKUP.dump --confirm-empty-target" >&2; exit 2; }
[ "$CONFIRM" = "--confirm-empty-target" ] || { echo "ERROR: restore requires an empty target and explicit confirmation" >&2; exit 2; }
[ -f "$DUMP.sha256" ] && (cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256")

compose() { docker compose --env-file "${PA_ENV_FILE:-$ROOT_DIR/deploy/production.env}" -f "$ROOT_DIR/compose.production.yaml" "$@"; }
compose stop api web
count=$(compose exec -T db psql --username pocket_alpha --dbname pocket_alpha --tuples-only --command "SELECT count(*) FROM pg_tables WHERE schemaname='public';")
[ "$(printf '%s' "$count" | tr -d '[:space:]')" = "0" ] || { echo "ERROR: target is not empty; create a fresh database volume" >&2; exit 1; }
compose exec -T db pg_restore --username pocket_alpha --dbname pocket_alpha --exit-on-error --no-owner --no-acl < "$DUMP"
compose run --rm migrate
compose up -d --wait --wait-timeout 240 api web proxy
echo "Restore complete. Perform the documented reconciliation and application smoke checks."
