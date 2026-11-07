# API integration inventory

Baseline: `1dd52d4`. Every existing FastAPI route is listed, including internal routes. Mobile access requires a separate authenticated allowlist; presence here does not authorize exposure.

| Method | Endpoint | Handler | Native baseline |
|---|---|---|---|
| GET | `/api/v1/markets/{market_id}/analysis` | `src/pocket_alpha/analysis/api.py:analysis` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/backtests/{run_id}` | `src/pocket_alpha/backtesting/api.py:report` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/context/{entity_id}` | `src/pocket_alpha/contextual/api.py:context` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/derivatives/contracts` | `src/pocket_alpha/derivatives/api.py:contracts` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/derivatives/term-structure` | `src/pocket_alpha/derivatives/api.py:curve` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/derivatives/option-skew` | `src/pocket_alpha/derivatives/api.py:skew` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/derivatives/{contract_id}/context` | `src/pocket_alpha/derivatives/api.py:context` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/assets/{asset_id}/fundamentals` | `src/pocket_alpha/fundamentals/api.py:snapshot` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/assets/{asset_id}/fundamental-context` | `src/pocket_alpha/fundamentals/api.py:context` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/markets/{market_id}/zones` | `src/pocket_alpha/intelligence/zones/api.py:zones` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/live-control` | `src/pocket_alpha/live_control/api.py:read_control` | BLOCKED — privileged operator control |
| PUT | `/api/v1/live-control` | `src/pocket_alpha/live_control/api.py:configure_control` | BLOCKED — privileged operator control |
| POST | `/api/v1/live-control/transitions` | `src/pocket_alpha/live_control/api.py:transition_control` | BLOCKED — privileged operator control |
| GET | `/health/live` | `src/pocket_alpha/main.py:live` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/health/ready` | `src/pocket_alpha/main.py:ready` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/assets` | `src/pocket_alpha/market_data/api.py:assets` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/assets/{asset_id}` | `src/pocket_alpha/market_data/api.py:asset` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/markets` | `src/pocket_alpha/market_data/api.py:markets` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/markets/{market_id}/candles` | `src/pocket_alpha/market_data/api.py:candles` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/paper/accounts` | `src/pocket_alpha/paper_trading/api.py:accounts` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/paper/accounts/{account_id}` | `src/pocket_alpha/paper_trading/api.py:account` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/portfolios` | `src/pocket_alpha/portfolio/api.py:portfolios` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| POST | `/api/v1/portfolios` | `src/pocket_alpha/portfolio/api.py:create_portfolio` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/portfolios/{portfolio_id}` | `src/pocket_alpha/portfolio/api.py:portfolio` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/portfolios/{portfolio_id}/entries` | `src/pocket_alpha/portfolio/api.py:entries` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| POST | `/api/v1/portfolios/{portfolio_id}/entries` | `src/pocket_alpha/portfolio/api.py:record_entry` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/portfolios/{portfolio_id}/snapshot` | `src/pocket_alpha/portfolio/api.py:snapshot` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/portfolios/{portfolio_id}/intelligence` | `src/pocket_alpha/portfolio_intelligence/api.py:recent` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| POST | `/api/v1/portfolios/{portfolio_id}/intelligence` | `src/pocket_alpha/portfolio_intelligence/api.py:create` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/portfolio-intelligence/{analysis_id}` | `src/pocket_alpha/portfolio_intelligence/api.py:get` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/research/reports/{report_id}` | `src/pocket_alpha/research/api.py:report` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/research/models/{artifact_id}` | `src/pocket_alpha/research/api.py:model` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| POST | `/api/v1/scans` | `src/pocket_alpha/scanner/api.py:create_scan` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/scans` | `src/pocket_alpha/scanner/api.py:recent_scans` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/scans/{scan_id}` | `src/pocket_alpha/scanner/api.py:scan` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/strategies` | `src/pocket_alpha/strategies/api.py:strategies` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/strategies/{strategy_id}` | `src/pocket_alpha/strategies/api.py:strategy` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/watchlists` | `src/pocket_alpha/watchlists/api.py:watchlists` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| POST | `/api/v1/watchlists` | `src/pocket_alpha/watchlists/api.py:create_watchlist` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/watchlists/{watchlist_id}` | `src/pocket_alpha/watchlists/api.py:watchlist` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| PATCH | `/api/v1/watchlists/{watchlist_id}` | `src/pocket_alpha/watchlists/api.py:rename_watchlist` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| PUT | `/api/v1/watchlists/{watchlist_id}/markets/{market_id}` | `src/pocket_alpha/watchlists/api.py:add_market` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| DELETE | `/api/v1/watchlists/{watchlist_id}/markets/{market_id}` | `src/pocket_alpha/watchlists/api.py:remove_market` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| POST | `/api/v1/watchlists/{watchlist_id}/snapshots` | `src/pocket_alpha/watchlists/api.py:capture_snapshot` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/watchlists/{watchlist_id}/snapshots/latest` | `src/pocket_alpha/watchlists/api.py:latest_snapshot` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |
| GET | `/api/v1/watchlists/{watchlist_id}/alerts` | `src/pocket_alpha/watchlists/api.py:alerts` | Native authenticated allowlist; route-specific coverage in TEST_EVIDENCE.md |

## Added native-only contracts

All paths below are relative to the `/mobile` boundary. They are not published on the original private root API.

| Method | Endpoint | Purpose / authorization |
|---|---|---|
| POST | `/api/v1/auth/login` | Provisioned workspace operator; Redis admission; short-lived/rotating credentials |
| POST | `/api/v1/auth/refresh` | Rotating opaque credential; replay revokes family |
| GET | `/api/v1/auth/sessions` | Authenticated owner device inventory |
| DELETE | `/api/v1/auth/sessions/{session_id}` | Authenticated owner revocation |
| POST | `/api/v1/auth/step-up` | Rate-limited password confirmation for manual accounting edits |
| GET | `/api/v1/markets/{market_id}/candles/latest` | Authenticated latest stored closed bar and actual age; no invented live quote |
| GET | `/api/v1/markets/{market_id}/analysis/snapshots` | Authenticated bounded keyset discovery, existing immutable reports |
| DELETE | `/api/v1/watchlists/{watchlist_id}` | Authenticated expected-revision archival; immutable history retained |
| GET | `/api/v1/status` | Authenticated capability status; no privileged journal/control access |

The exact generated contract is `native-openapi.json`; CI rejects drift. Original `/health/**` and `/api/v1/live-control/**` are excluded from the native boundary. Backtest/research POST job routes, operational execution monitoring, full sync and push contracts do not exist and are not simulated.
