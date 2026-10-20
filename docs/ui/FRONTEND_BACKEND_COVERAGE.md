# Frontend/backend coverage

| Surface | Contract | UI state and persistence |
|---|---|---|
| Market catalogue/search | `GET /api/v1/markets`, `GET /api/v1/assets/{id}` | Loading, empty, error, pagination; stored catalogue |
| Chart/zones | `GET /api/v1/markets/{id}/candles|zones` | Loading, invalid quality, empty, provider error, provenance, UTC; stored observations |
| Analyze | `GET /api/v1/markets/{id}/analysis` | Available/unavailable/partial horizons; immutable snapshot |
| Watchlists | `/api/v1/watchlists/**` | Create, membership, snapshot and alert reads; PostgreSQL revision semantics |
| Scanner | `/api/v1/scans/**` | Persisted scan, no-match and exclusions; causal Analyze inputs |
| Portfolio | `/api/v1/portfolios/**` | Manual ledger, snapshots and intelligence; Decimal server accounting |
| PAPER | `GET /api/v1/paper/accounts/**` | Empty/unavailable/ready; simulated ledger only |
| Strategies | `GET /api/v1/strategies/**` | Read-only contract page; no lifecycle mutation contract |
| Backtesting | `GET /api/v1/backtests/{id}` | Known-run retrieval only; no authenticated scheduler contract |
| Research | `GET /api/v1/research/reports|models/{id}` | Artifact inspection only |
| Health | `GET /health/ready` through `/api/system/ready` | Loading/ready/unavailable; no-store |
| Risk/execution/autopilot | No public mutation endpoint | Safety-boundary page; browser cannot authorize or dispatch |
| Fundamentals/context/derivatives | Backend GET contracts exist | Not yet promoted to primary interactive widgets; API-only, recorded debt |

The Next gateway allowlists paths, methods and query keys, limits mutation bodies, rejects redirects and sanitizes upstream errors. Authentication is supplied by the production reverse proxy. Pagination is bounded by each schema. Freshness is expressed through `as_of`, candle close, received and quality timestamps; no client-side trading authorization or financial computation is authoritative.
