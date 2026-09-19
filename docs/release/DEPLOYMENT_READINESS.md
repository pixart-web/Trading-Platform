# Deployment readiness

## Current state

`DEPLOYMENT_READY = YES`

`READY_STATE = READY_WITH_NON_BLOCKING_DEBT`

`REAL_MONEY_TRADING_READY = NO`

The candidate is scoped to a single-operator research, read-only and PAPER deployment. Live spot, Autopilot real operation and derivative execution remain disabled through `Literal[False]` settings and explicit production environment values.

## Satisfied repository controls

- Caddy is the only service with host ports in `compose.production.yaml`.
- TLS is automatic for a valid public domain; bcrypt Basic Auth protects the complete frontend.
- Frontend reaches an internal-only API; API reaches internal-only PostgreSQL and password-protected Redis.
- Connection strings are mounted as Docker secret files and redacted by Pydantic.
- API/web run non-root, with read-only filesystems, dropped capabilities and healthchecks.
- Migrations run as a one-shot dependency before API startup.
- PostgreSQL and Caddy state use named volumes; Redis is deliberately disposable and non-persistent; no database/cache port is published.
- CI verifies config, builds, critical image CVEs, startup, probes, authentication and restore.

## Manual prerequisites before deployment

1. Provision a supported Linux host with current Docker Engine and Compose plugin.
2. Point the chosen domain to the host; allow inbound 80/443 and restrict SSH to operator networks.
3. Create `/srv/pocket-alpha/secrets` root-owned mode 700. Keep all secret files root-owned mode 444; Compose mounts each file read-only only into its authorized service.
4. Generate independent random PostgreSQL and Redis passwords and matching connection URLs.
5. Generate a Caddy bcrypt password hash; never commit plaintext or the production env file.
6. Provision encrypted off-server backup storage, log shipping, uptime probes, disk/CPU/memory alerts and an alert recipient.
7. Record resolved image digests, the approved Git SHA and rollback SHA.
8. Take and verify a pre-migration PostgreSQL backup.
9. Run `docker compose -f compose.production.yaml config` and the release checklist.
10. Obtain a separate explicit deployment authorization. This audit does not deploy.

## Blocker policy

The audited candidate CI is green. Any later non-green CI job, missing backup destination, failed restore rehearsal, absent TLS/domain, inability to protect secret files, public API/data port, or changed execution flag makes the state `NOT_READY`. Missing real-money evidence does not block this limited mode because real execution remains off.
