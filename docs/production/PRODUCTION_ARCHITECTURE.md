# Production architecture

Internet → Caddy TLS/basic authentication → Next.js → internal FastAPI → internal PostgreSQL/Redis. Only Caddy publishes host ports (80, 443 TCP and 443 UDP). Application and data networks are isolated; API and web run read-only, without capabilities, with `no-new-privileges`. PostgreSQL is the durable ledger; Redis is disposable coordination state.

The supported initial operating modes are RESEARCH and PAPER. LIVE_READ_ONLY remains an operator CLI/private evidence workflow. Live spot, derivatives and autopilot are structurally disabled and have no public HTTP submission route. The modular order remains market data → intelligence → forecasts → directional analysis → strategy → portfolio → risk → leverage assessment → execution → broker.

Single-operator bcrypt Basic Auth is a scope constraint. Multi-user operation requires SSO/MFA, application roles and an identity audit trail before exposure.
