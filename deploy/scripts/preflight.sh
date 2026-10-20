#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE="$ROOT_DIR/compose.production.yaml"
ENV_FILE=${PA_ENV_FILE:-$ROOT_DIR/deploy/production.env}

[ -f "$ENV_FILE" ] || { echo "ERROR: create the protected production environment file at $ENV_FILE" >&2; exit 1; }
set -a
# This operator-owned file is trusted configuration; quote values containing '$'.
. "$ENV_FILE"
set +a

command -v docker >/dev/null 2>&1 || { echo "ERROR: docker is required" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: docker compose v2 is required" >&2; exit 1; }

: "${PA_DOMAIN:?set PA_DOMAIN}"
: "${PA_ADMIN_USER:?set PA_ADMIN_USER}"
: "${PA_ADMIN_PASSWORD_HASH:?set PA_ADMIN_PASSWORD_HASH}"

case "$PA_DOMAIN" in research.example.com|example.com|"") echo "ERROR: set the approved DNS name" >&2; exit 1;; esac
case "$PA_ADMIN_PASSWORD_HASH" in \$2a\$*|\$2b\$*|\$2y\$*) :;; *) echo "ERROR: PA_ADMIN_PASSWORD_HASH must be a bcrypt hash" >&2; exit 1;; esac

for variable in PA_DATABASE_URL_SECRET_FILE PA_REDIS_URL_SECRET_FILE PA_POSTGRES_PASSWORD_SECRET_FILE PA_REDIS_PASSWORD_SECRET_FILE; do
  eval "secret_path=\${$variable:-}"
  [ -n "$secret_path" ] && [ -f "$secret_path" ] && [ -s "$secret_path" ] || { echo "ERROR: $variable must name a non-empty file" >&2; exit 1; }
done

config=$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config)
printf '%s\n' "$config" | grep -q 'PA_LIVE_TRADING_ENABLED: "false"' || { echo "ERROR: live spot guard changed" >&2; exit 1; }
printf '%s\n' "$config" | grep -q 'PA_DERIVATIVE_EXECUTION_ENABLED: "false"' || { echo "ERROR: derivative guard changed" >&2; exit 1; }
published=$(printf '%s\n' "$config" | grep -c 'published:' || true)
[ "$published" -eq 3 ] || { echo "ERROR: only Caddy 80/443 TCP+UDP may be published" >&2; exit 1; }

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet
echo "Preflight passed for RESEARCH/PAPER deployment. No service was changed."
