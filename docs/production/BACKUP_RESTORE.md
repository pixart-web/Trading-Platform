# Backup and restore

`deploy/scripts/backup.sh` creates a UTC-named PostgreSQL custom-format dump with mode-restrictive umask and SHA-256 sidecar. Schedule at least daily, copy encrypted to an off-server target, retain according to operator policy and monitor age/size. Caddy state should be protected separately or certificates can be reissued.

Restore only into an empty target with `restore.sh BACKUP.dump --confirm-empty-target`. The script verifies the checksum when present, stops API/web, rejects a non-empty public schema, restores with `--exit-on-error`, runs migrations and waits for service health. Then reconcile ledger counts, latest timestamps, portfolio snapshots and application workflows. A dump is not accepted until a disposable restore drill succeeds.

RPO/RTO must be set by the owner based on scheduled frequency, database size and measured drills; none is fabricated here.
