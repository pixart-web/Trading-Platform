#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
BACKUP_DIR=${PA_BACKUP_DIR:-/srv/pocket-alpha/backups}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="$BACKUP_DIR/pocket-alpha-$STAMP.dump"
mkdir -p "$BACKUP_DIR"
umask 077
docker compose --env-file "${PA_ENV_FILE:-$ROOT_DIR/deploy/production.env}" -f "$ROOT_DIR/compose.production.yaml" exec -T db \
  pg_dump --username pocket_alpha --dbname pocket_alpha --format=custom --no-owner --no-acl > "$TARGET"
test -s "$TARGET"
sha256sum "$TARGET" > "$TARGET.sha256"
echo "Backup created: $TARGET"
