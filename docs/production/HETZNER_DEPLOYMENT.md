# Hetzner deployment

No server was modified by this release. The target is a dedicated Linux host shared only through isolated Docker networks and explicit host ports.

1. Provision current Debian/Ubuntu, Docker Engine with Compose v2, an unprivileged operator, root-owned `/srv/pocket-alpha/{secrets,backups}` and an off-server encrypted backup target.
2. Point approved DNS A/AAAA records at the host. Permit inbound 22 only from the operator network and 80/443 publicly; deny database/Redis/API ports.
3. Copy `deploy/production.env.example` outside Git as `deploy/production.env`; create the four secret files named there with directory mode 700 and file mode 400/440.
4. Generate a unique bcrypt operator hash with the documented Caddy command. Do not reuse broker credentials and do not grant withdrawal permissions.
5. Run `deploy/scripts/preflight.sh`, then `deploy/scripts/deploy.sh --dry-run`.
6. In an approved window only, run `deploy/scripts/deploy.sh --apply`; verify certificate, unauthenticated 401, authenticated dashboard, readiness, migrations and RESEARCH/PAPER workflows.

Required external values: host/IP, approved domain, DNS control, operator SSH and bcrypt credentials, off-server backup location, monitoring/alert receiver. Broker venue and credentials are not deployment prerequisites for RESEARCH/PAPER.

Phase 30 additionally requires a random 32+ character `control_proxy_token` secret shared only by
the web and API containers. Deployment flags default false. Setting either gate true requires the
matching explicit preflight acknowledgement and still cannot activate LIVE without the persistent
operator state, current qualification evidence, risk approval and clear kill switch.
