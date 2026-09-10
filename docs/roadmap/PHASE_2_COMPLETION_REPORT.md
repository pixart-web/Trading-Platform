# Phase 2 — Charting Foundation

## Scope and assessment
Phase 1 was complete and the tree clean. No frontend or real provider existed. This task adds
only the Phase 2 frontend, backward-compatible API search, Docker/CI integration and tests.
No migrations, risk logic, forecasts, indicators, portfolio features or trading were introduced.

## Architecture and files
See docs/architecture/CHARTING_ARCHITECTURE.md. The shared FastAPI engine remains authoritative;
Next.js visualizes validated historical data via a bounded GET-only gateway. Asset search,
timeframe selection, UTC ranges, candlesticks/volume, zoom/crosshair, exact-value tables, loading,
empty, error and quality-rejection states are implemented.

Created:
- frontend/package.json
- frontend/pnpm-lock.yaml
- frontend/pnpm-workspace.yaml
- frontend/tsconfig.json
- frontend/next-env.d.ts
- frontend/next.config.ts
- frontend/eslint.config.mjs
- frontend/.env.example
- frontend/.dockerignore
- frontend/Dockerfile
- frontend/NOTICE
- frontend/app/layout.tsx
- frontend/app/page.tsx
- frontend/app/globals.css
- frontend/app/api/market-data/[...path]/route.ts
- frontend/components/market-workspace.tsx
- frontend/components/price-chart.tsx
- frontend/lib/market-data.ts
- frontend/lib/proxy.ts
- frontend/vitest.config.ts
- frontend/playwright.config.ts
- frontend/tests/market-data.test.ts
- frontend/tests/proxy-route.test.ts
- frontend/e2e/workspace.spec.ts
- docs/architecture/CHARTING_ARCHITECTURE.md
- docs/roadmap/PHASE_2_COMPLETION_REPORT.md

Modified:
- src/pocket_alpha/market_data/api.py
- tests/test_market_api.py
- .gitignore
- pyproject.toml (exclude generated frontend dependencies from Python discovery)
- compose.yaml
- .github/workflows/ci.yml
- README.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md

## Verification
Local backend: 102 passed, 32 skipped because PostgreSQL is not configured locally; 99% statement
coverage, API module 100%. Financial calculations are unchanged; no new economic metrics exist.
Frontend tests: 37 contract and gateway cases passed. Seven Playwright cases passed on installed Edge:
empty installation, search/select/price+volume/timeframe/table, quality rejection, service errors,
invalid ranges, mobile chart and mobile empty layout. Synthetic fixtures are explicitly test-only.
Two initial browser failures were ambiguous selectors (chart's internal table and Next's announcer);
selectors were narrowed to the intended elements without weakening assertions.

Commands: pnpm install, pnpm lint, pnpm typecheck, pnpm test, pnpm build, pnpm test:e2e;
ruff check ., ruff format --check ., mypy ., pytest --cov=pocket_alpha --cov-report=term-missing.
Local equivalents use bundled node executables for eslint/bin/eslint.js, typescript/bin/tsc,
vitest/vitest.mjs, next/dist/bin/next and @playwright/test/cli.js. Python runs through .venv.
Package installation initially failed under network sandboxing; approved installation succeeded.
The esbuild compiler required approved execution outside the sandbox. Chromium download failed
with DNS errors; PA_TEST_BROWSER_CHANNEL=msedge selected the installed browser for local E2E.
Docker is unavailable locally. Remote CI verifies PostgreSQL/Redis, migrations, Compose and both
images and repeats frontend checks with Chromium. Final results are appended after verification.

## Security, assumptions, limitations and debt
No trading credentials, secrets, external data provider or fake production data. Live trading stays
blocked. The API URL is server-only; errors do not expose upstream payloads/connection details.
Production authentication/rate limiting remain existing debt; Compose binds host ports to loopback.
Historical age is explicitly allowed by the Phase 1 policy, not presented as live freshness.
Canvas numbers approximate Decimal values; exact strings remain available. Continuous-grid session
limitations remain and may suppress legitimate session-based charts rather than hide gaps.
The latest dependency resolution retains ESLint 9 compatibility with the Next.js preset, although
the package manager reports its deprecation. Upstream Python warnings remain. No economic
performance is asserted. Public site deployment was not part of this repository phase.

Next phase: 3 — deterministic, causal, versioned technical features in the backend, with testable
indicator framework. It is not started here. Real-data provider integration remains separately
scoped; the chart must remain empty until legitimate stored observations are available.
