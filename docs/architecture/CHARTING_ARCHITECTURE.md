# Phase 2 — charting foundation

Next.js App Router / React / TypeScript live in frontend/. FastAPI remains the sole market-data
and future analytical backend. No separate persistence, forecasts, indicators, positions or order
routes are introduced. The frontend is an interactive historical working surface, not a live feed.

The server-only PA_API_BASE_URL configures the existing API origin. A GET-only Next.js gateway
allows only assets, markets and candle paths, forwards an explicit query allowlist, blocks path
traversal and redirects, applies an eight-second timeout, sanitizes errors and disables caching.
Internal service configuration is not exposed through NEXT_PUBLIC variables. This is local/private
deployment infrastructure, not a public production API gateway with authentication or rate limits.

FastAPI search now accepts bounded q on assets/markets and asset_type on markets. Search is
case-insensitive across symbol/name, escapes wildcard characters, and retains bounded pagination.
No schema changes or migrations. Existing clients continue to work with default parameters.

The browser runtime-validates response shape, decimal strings, finite plotting values, OHLC and
timestamps. It blocks plotting if backend quality fails, responses are truncated, identities or
timeframes mismatch, records are duplicated/out of order, or expected continuous slots are missing.
It does not repair, sort or fabricate observations. Failed/empty requests never become zero prices.
All fetches are cancellable; result keys and refresh revisions keep previous data off a newly
selected market or timeframe. A twelve-second browser timeout bounds waiting for the gateway.

Supported timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w. Initial ranges contain 200 completed
nominal candles and custom ranges are limited to 1,000. End is exclusive; date controls explicitly
use UTC. Weekly defaults are Monday-anchored. Phase 1's fixed 24h/7d and continuous-grid limitations
remain; missing closed-session slots block charting until a session-aware policy is added.

Lightweight Charts renders candlestick and histogram panes with shared time scale, crosshair,
pan/zoom and fit controls. No technical calculations are introduced. Decimal strings remain
unchanged in the exact-values table and latest-close/hover text. JavaScript numbers are used only
for approximate canvas coordinates. Historical last close is never labelled a live quote.
Library attribution is present in the UI and frontend/NOTICE.

Reference APIs used:
- https://tradingview.github.io/lightweight-charts/docs/series-types
- https://nextjs.org/docs/app/getting-started/installation

The layout includes keyboard-labelled controls, visible focus, a skip link, semantic table fallback,
screen-reader status/error text, reduced-motion support and responsive layouts. No synthetic data
is shipped to production; test fixtures are confined to frontend/tests and frontend/e2e.

Compose adds a loopback-bound web service at port 3000. Docker builds standalone output with
PA_STANDALONE=1 and runs as the node user. Standard local build/start uses Next.js normally.
pnpm version and package lock are committed; only esbuild and unrs-resolver install scripts are
approved. Node 24 is the tested runtime. CI adds lint, TypeScript, Vitest, production build,
Playwright Chromium tests and frontend Docker build alongside all previous backend checks.

Phase 5 extends the gateway allowlist with the read-only zones route. Enabling the zones control
replaces the candle request with one atomic candles/snapshot request, using the same cancellation
and quality gates plus zone identity, availability, exact bounds and component checks. Baseline
series shade fixed bands from current-role availability, never from the earlier pivot position.
An exact-values evidence table remains available; late imports outside the plotted history do not
produce a retrospective band. See SUPPORT_RESISTANCE.md. Analytics remain entirely in Python.
