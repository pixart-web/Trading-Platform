# Operations runbook

Daily: verify HTTPS, authenticated login, `/health/ready`, container health/restarts, PostgreSQL storage growth, backup age/size/checksum, certificate expiry, provider freshness and alert delivery. Weekly: review dependency/image advisories, restore the latest backup into a disposable empty database, inspect journals and capacity. Monthly: patch the host in an approved window and exercise rollback/incident communications.

Incident order: suspend external access if identity is suspect; preserve logs/journals; keep live flags false; classify database, provider, application or host failure; stop only the affected edge/application services; recover from a known release or verified backup; run migrations and reconciliation; verify data timestamps and accounting before reopening.

Commands use `docker compose --env-file deploy/production.env -f compose.production.yaml`. Use `ps`, `logs --since`, `exec db pg_isready`, and authenticated HTTPS smoke checks. Never print secret files or database URLs. A restart must never alter execution permissions.
