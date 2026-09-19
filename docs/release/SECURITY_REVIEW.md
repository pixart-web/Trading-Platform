# Security review

## Threat boundary

The intended deployment is one trusted operator over HTTPS. Browser traffic terminates at Caddy. Caddy authenticates before forwarding to Next.js. Next.js exposes a fixed allowlisted gateway to FastAPI. FastAPI, PostgreSQL and Redis have no host ports in production. There are no HTTP routes for spot execution, derivative execution, broker credentials, withdrawals or Autopilot control.

## Route classification

| Surface | Classification | Rationale |
|---|---|---|
| Caddy `/` and frontend static/application routes | AUTH_REQUIRED | Whole research workspace contains portfolio and research state. |
| Next `/api/market-data/**` GET/POST/PUT/PATCH/DELETE allowlist | AUTH_REQUIRED | Reads private local state and permits bounded portfolio/watchlist/scan mutations. Caddy protects it. |
| FastAPI analytical `/api/v1/**` routes | INTERNAL_ONLY | Analytical data can be sensitive and has no app identity layer. Reachable only from frontend network. |
| FastAPI portfolio/watchlist/scanner routes | INTERNAL_ONLY | State-changing/accounting-like records; never publish directly. |
| FastAPI backtest/research/strategy/PAPER GET routes | INTERNAL_ONLY | Research evidence and simulated account state. |
| `/health/live` | INTERNAL_ONLY by current topology | Container/proxy probes only. A load balancer may receive a separately approved path later. |
| `/health/ready` | INTERNAL_ONLY | Reveals dependency state and performs database/Redis checks. |
| FastAPI docs/OpenAPI | INTERNAL_ONLY | Operational schema, not exposed by Caddy routing. |
| Broker-read-only CLI and private observation files | NEVER_EXPOSE | Credentials and account evidence remain local/operator-only. |
| Spot/derivative journals and execution classes | NEVER_EXPOSE | No HTTP route exists; real dispatch remains structurally blocked. |
| PostgreSQL/Redis | NEVER_EXPOSE | Internal network only; firewall and Compose publish no ports. |

## Controls reviewed

- Secrets: `.env*`, keys and `.private/` are ignored; Dockerfiles copy only selected source/config. SecretStr fields exclude representation; new file-secret validation gives content-free errors.
- Browser: CSP, frame denial, MIME sniff prevention, no-referrer and restricted permissions are set; Playwright verifies headers. No raw HTML sink, browser token storage, open redirect or service worker was found.
- Proxy: path/method/query allowlists, fixed server-side upstream, no credentials in URLs, redirect refusal, 8 KiB mutation limit, eight-second timeout, sanitized upstream errors and no-store responses.
- Backend: bounded Pydantic inputs and pagination, no CORS middleware, no cookie session/CSRF coupling, SQLAlchemy/parameterized SQLite, no eval/exec/shell or unsafe pickle/YAML.
- Outbound HTTP: HTTPS only, bounded bytes/timeouts/retries, rejected redirects, fixed SEC origin and provider identity checks. Network imports never run at startup.
- Containers: non-root API/web, read-only application filesystems, no-new-privileges, dropped capabilities, internal data networks and healthchecks.
- Credentials/brokers: broker secrets are environment-only and excluded from models/logs; withdrawals/transfers have no capability. Native derivative network code is absent.
- Supply chain: exact Python locks and frozen pnpm lock, SHA-pinned Actions, scanners in CI. Version-family base image tags remain recorded debt.

## Scanner evidence

- Bandit 1.9.4: zero medium/high findings after remediation.
- pip-audit 2.10.1: no known vulnerability in runtime or development locks after pytest upgrade.
- pnpm audit production: no known vulnerability.
- detect-secrets 1.5.0: audited baseline for local/synthetic values; hook rejects new candidates.
- Git history high-signal scan: one synthetic logging-test value, no verified secret.
- Trivy 0.74.0: final result is recorded by GitHub CI; critical findings fail the run.

## Residual constraints

Basic Auth is acceptable only for the stated single-operator deployment over TLS with a strong unique password and restricted firewall. Multi-user access requires an identity-aware proxy/SSO, MFA, roles, session controls and audit of user identity. Native rate limiting/WAF is not configured; the authenticated single-user scope and firewall are mandatory. A penetration test has not been performed.
