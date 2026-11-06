# API integration inventory

Baseline: `1dd52d4`. Every existing FastAPI route is listed, including internal routes. Mobile access requires a separate authenticated allowlist; presence here does not authorize exposure.

| Method | Endpoint | Handler | Native baseline |
|---|---|---|---|
| GET | `/api/v1/markets/{market_id}/analysis` | `src/pocket_alpha/analysis/api.py:analysis` | Not yet verified |
| GET | `/api/v1/backtests/{run_id}` | `src/pocket_alpha/backtesting/api.py:report` | Not yet verified |
| GET | `/api/v1/context/{entity_id}` | `src/pocket_alpha/contextual/api.py:context` | Not yet verified |
| GET | `/api/v1/derivatives/contracts` | `src/pocket_alpha/derivatives/api.py:contracts` | Not yet verified |
| GET | `/api/v1/derivatives/term-structure` | `src/pocket_alpha/derivatives/api.py:curve` | Not yet verified |
| GET | `/api/v1/derivatives/option-skew` | `src/pocket_alpha/derivatives/api.py:skew` | Not yet verified |
| GET | `/api/v1/derivatives/{contract_id}/context` | `src/pocket_alpha/derivatives/api.py:context` | Not yet verified |
| GET | `/api/v1/assets/{asset_id}/fundamentals` | `src/pocket_alpha/fundamentals/api.py:snapshot` | Not yet verified |
| GET | `/api/v1/assets/{asset_id}/fundamental-context` | `src/pocket_alpha/fundamentals/api.py:context` | Not yet verified |
| GET | `/api/v1/markets/{market_id}/zones` | `src/pocket_alpha/intelligence/zones/api.py:zones` | Not yet verified |
| GET | `/api/v1/live-control` | `src/pocket_alpha/live_control/api.py:read_control` | BLOCKED — privileged operator control |
| PUT | `/api/v1/live-control` | `src/pocket_alpha/live_control/api.py:configure_control` | BLOCKED — privileged operator control |
| POST | `/api/v1/live-control/transitions` | `src/pocket_alpha/live_control/api.py:transition_control` | BLOCKED — privileged operator control |
| GET | `/health/live` | `src/pocket_alpha/main.py:live` | Not yet verified |
| GET | `/health/ready` | `src/pocket_alpha/main.py:ready` | Not yet verified |
| GET | `/api/v1/assets` | `src/pocket_alpha/market_data/api.py:assets` | Not yet verified |
| GET | `/api/v1/assets/{asset_id}` | `src/pocket_alpha/market_data/api.py:asset` | Not yet verified |
| GET | `/api/v1/markets` | `src/pocket_alpha/market_data/api.py:markets` | Not yet verified |
| GET | `/api/v1/markets/{market_id}/candles` | `src/pocket_alpha/market_data/api.py:candles` | Not yet verified |
| GET | `/api/v1/paper/accounts` | `src/pocket_alpha/paper_trading/api.py:accounts` | Not yet verified |
| GET | `/api/v1/paper/accounts/{account_id}` | `src/pocket_alpha/paper_trading/api.py:account` | Not yet verified |
| GET | `/api/v1/portfolios` | `src/pocket_alpha/portfolio/api.py:portfolios` | Not yet verified |
| POST | `/api/v1/portfolios` | `src/pocket_alpha/portfolio/api.py:create_portfolio` | Not yet verified |
| GET | `/api/v1/portfolios/{portfolio_id}` | `src/pocket_alpha/portfolio/api.py:portfolio` | Not yet verified |
| GET | `/api/v1/portfolios/{portfolio_id}/entries` | `src/pocket_alpha/portfolio/api.py:entries` | Not yet verified |
| POST | `/api/v1/portfolios/{portfolio_id}/entries` | `src/pocket_alpha/portfolio/api.py:record_entry` | Not yet verified |
| GET | `/api/v1/portfolios/{portfolio_id}/snapshot` | `src/pocket_alpha/portfolio/api.py:snapshot` | Not yet verified |
| GET | `/api/v1/portfolios/{portfolio_id}/intelligence` | `src/pocket_alpha/portfolio_intelligence/api.py:recent` | Not yet verified |
| POST | `/api/v1/portfolios/{portfolio_id}/intelligence` | `src/pocket_alpha/portfolio_intelligence/api.py:create` | Not yet verified |
| GET | `/api/v1/portfolio-intelligence/{analysis_id}` | `src/pocket_alpha/portfolio_intelligence/api.py:get` | Not yet verified |
| GET | `/api/v1/research/reports/{report_id}` | `src/pocket_alpha/research/api.py:report` | Not yet verified |
| GET | `/api/v1/research/models/{artifact_id}` | `src/pocket_alpha/research/api.py:model` | Not yet verified |
| POST | `/api/v1/scans` | `src/pocket_alpha/scanner/api.py:create_scan` | Not yet verified |
| GET | `/api/v1/scans` | `src/pocket_alpha/scanner/api.py:recent_scans` | Not yet verified |
| GET | `/api/v1/scans/{scan_id}` | `src/pocket_alpha/scanner/api.py:scan` | Not yet verified |
| GET | `/api/v1/strategies` | `src/pocket_alpha/strategies/api.py:strategies` | Not yet verified |
| GET | `/api/v1/strategies/{strategy_id}` | `src/pocket_alpha/strategies/api.py:strategy` | Not yet verified |
| GET | `/api/v1/watchlists` | `src/pocket_alpha/watchlists/api.py:watchlists` | Not yet verified |
| POST | `/api/v1/watchlists` | `src/pocket_alpha/watchlists/api.py:create_watchlist` | Not yet verified |
| GET | `/api/v1/watchlists/{watchlist_id}` | `src/pocket_alpha/watchlists/api.py:watchlist` | Not yet verified |
| PATCH | `/api/v1/watchlists/{watchlist_id}` | `src/pocket_alpha/watchlists/api.py:rename_watchlist` | Not yet verified |
| PUT | `/api/v1/watchlists/{watchlist_id}/markets/{market_id}` | `src/pocket_alpha/watchlists/api.py:add_market` | Not yet verified |
| DELETE | `/api/v1/watchlists/{watchlist_id}/markets/{market_id}` | `src/pocket_alpha/watchlists/api.py:remove_market` | Not yet verified |
| POST | `/api/v1/watchlists/{watchlist_id}/snapshots` | `src/pocket_alpha/watchlists/api.py:capture_snapshot` | Not yet verified |
| GET | `/api/v1/watchlists/{watchlist_id}/snapshots/latest` | `src/pocket_alpha/watchlists/api.py:latest_snapshot` | Not yet verified |
| GET | `/api/v1/watchlists/{watchlist_id}/alerts` | `src/pocket_alpha/watchlists/api.py:alerts` | Not yet verified |
