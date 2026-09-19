# Pocket Alpha

Phase 17 adds immutable portfolio-intelligence reports over exact Phase 16 state: allocation,
concentration, effective diversification, non-annualized volatility, correlations, optional beta and
risk contribution use causal stored data. Unsupported sector, liquidity, drawdown, regime and horizon
metrics stay explicitly unavailable. Migration 0008 is additive. See
[portfolio intelligence](docs/architecture/PORTFOLIO_INTELLIGENCE.md).
Phase 16 adds persistent manual portfolios, immutable deposits/withdrawals/buys/sells, exact
moving-average accounting and causal as-of valuation from stored candles. Missing prices remain
explicit and prevent aggregate valuation; manual records are not orders, fills, recommendations or
risk approvals. Migration 0007 is additive. See
[portfolio architecture](docs/architecture/PORTFOLIO.md).

Phase 15 adds immutable cross-market scans over exact stored Analyze reports. Metadata and economic
filters produce deterministic Opportunity Score rankings kept separate by policy version/hash, while
every non-ranked market retains explicit exclusion reasons. The web workspace validates and shows exact
values; results are not probabilities, recommendations or risk approvals. Migration 0006 is additive.
See [scanner architecture](docs/architecture/SCANNER.md).
Phase 14 adds persistent local watchlists, optimistic revisions, immutable exact-time Analyze snapshots
and append-only transition events. The web workspace can organize registered markets and inspect honest
coverage or changed horizon conclusions. Events do not send notifications and are not recommendations
or risk approvals. Migration 0005 is additive. See
[watchlist architecture](docs/architecture/WATCHLISTS.md).

Phase 13 adds the shared Analyze experience: immutable reports combine Pocket Score and all thirteen
forecast horizons with their forecasts, independent directional cases and net economic opportunity
assessment. Migration 0004 stores append-only snapshots; a read-only API and validated responsive
web panel show exact evidence, opposition, uncertainty, reasons and versions, or honest
unavailability when no snapshot exists. See [Analyze architecture](docs/architecture/ANALYZE.md).

Phase 12 adds a versioned Opportunity Score for one directional trade and forecast horizon after
explicit fees, spread, slippage and latency. Calibrated probability, expected move, liquidity,
uncertainty and risk/reward remain explained; economic gates determine eligibility and deterministic
rankings exclude unavailable or ineligible opportunities. The score is not a probability,
recommendation or risk approval. See
[Opportunity Score architecture](docs/architecture/OPPORTUNITY_SCORE.md).

Phase 11 adds independent LONG and SHORT criterion evaluation with explicit NO_TRADE outcomes
for conflict, failed cases and incomplete evidence. Policies, thresholds, source evidence and
reasons remain inspectable; broker capabilities cannot alter analysis. See
[directional analysis](docs/architecture/DIRECTIONAL_ANALYSIS.md).

Phase 10 adds a configurable, explained Pocket Score over versioned normalized setup-quality
components. Missing required evidence fails closed; weights, coverage and contributions remain
inspectable. The score is not a probability, direction, recommendation or economic ranking. See
[Pocket Score architecture](docs/architecture/POCKET_SCORE.md).

Phase 9 adds an interpretable research forecast baseline, separate temperature calibration and
cost-aware temporal evaluation over explicit train/calibration/validation/final-holdout partitions.
Artifacts retain causal cutoffs, versions and hashes; predictions use the immutable Phase 8
forecast contract. Tests use synthetic fixtures, and no accuracy, calibration or profitability is
claimed. See [baseline forecast models](docs/architecture/BASELINE_FORECAST_MODELS.md).

Phase 8 adds a validated append-only forecast ledger, immutable causal evidence snapshots, separate
post-expiry outcomes and deterministic reference metrics. It accepts externally produced forecasts
and does not ship a forecast model or fabricate predictions. See
[forecast architecture](docs/architecture/FORECAST_ARCHITECTURE.md). Migration 0003 adds forecast
and outcome tables; no forecast API/UI, score, strategy or execution path exists.

Phase 7 adds a shared [regime engine](docs/architecture/REGIME_ENGINE.md): explained trend and
volatility classifications, explicit supervised research probabilities and temporal held-out
evaluation. No trained model or real dataset is shipped; probabilities are unavailable without
a supplied model and remain explicitly uncalibrated when modeled. This is a Python service only.

Phase 6: causal multi-timeframe context with independent technical, structure and zone analyses,
explicit agreement/disagreement and higher-timeframe opposition over trusted replay.
See [multi-timeframe intelligence](docs/architecture/MULTI_TIMEFRAME.md) for the shared Python
service, cutoff/freshness contracts and usage. This service is not yet exposed in the UI/API.
Phase 5 support/resistance zones retain explained strength and optional chart overlays.
The Phase 2 Next.js workspace provides search, candles, volume and quality states.
No external provider is connected and no market data is seeded. No signals or execution exist.
See [market-data architecture](docs/architecture/MARKET_DATA_ARCHITECTURE.md).
See [technical intelligence](docs/architecture/TECHNICAL_INTELLIGENCE.md) for backend usage,
formula conventions and the implemented catalogue. Indicators are not yet exposed in the UI/API.
See [market structure](docs/architecture/MARKET_STRUCTURE.md) for backend usage and exact
confirmation/break conventions. Structure is not yet exposed in the UI/API either.
See [support/resistance](docs/architecture/SUPPORT_RESISTANCE.md) for zone conventions,
the atomic candles/zones API and availability-gated overlays. Strength is not a probability.

## Development

Install Python 3.12+ and Docker Compose. Create a virtual environment with
`python -m venv .venv` and activate it (`.venv\Scripts\Activate.ps1` on Windows).
Run `pip install -r requirements.lock` then `pip install --no-deps -e .`.
Start the stack with `docker compose up --build -d`. API docs: http://localhost:8000/docs.
Probes: `/health/live` and `/health/ready`. Compose runs migrations before the API starts.
For host development, start `docker compose up -d db redis`, copy `.env.example` to `.env`,
run `alembic upgrade head`, then `uvicorn pocket_alpha.main:app --no-access-log`.
Sample credentials and loopback bindings are for local development, not production deployment.

The charting interface runs at http://localhost:3000 when using Compose. Without imported market
metadata/data it displays honest empty states. With the backend stopped it displays a service error.
For frontend-only development, install Node 24 and pnpm 11.19.0, then run in frontend/:

    pnpm install --frozen-lockfile
    pnpm dev

Copy frontend/.env.example to frontend/.env.local to change the server-only backend origin.
Frontend checks: pnpm lint, pnpm typecheck, pnpm test, pnpm build.
Browser tests: pnpm exec playwright install chromium, then pnpm test:e2e.
Tests use synthetic fixtures only and never import them into application data.
For a local installed Edge browser, set PA_TEST_BROWSER_CHANNEL=msedge.
See docs/architecture/CHARTING_ARCHITECTURE.md for quality gating and timezone semantics.

Checks: `ruff check .`, `ruff format --check .`, `mypy .`,
`pytest --cov=pocket_alpha --cov-report=term-missing`.
Integration requires PostgreSQL and Redis and `PA_INTEGRATION=1` (enabled in CI).
Use a disposable database: the integration test downgrades and deletes its audit history.
Never run this integration test against retained data.

## Market-data inspection

`GET /api/v1/assets`, `GET /api/v1/assets/{asset_id}`, `GET /api/v1/markets` and
`GET /api/v1/markets/{market_id}/candles?timeframe=1h&start=2025-01-01T00:00:00Z&end=2025-01-02T00:00:00Z&limit=100`.
Unknown identities return 404; empty lists are expected until metadata is registered.
Candles include quality, truncation and continuation information. Invalid/incomplete data is
diagnostic only. The API uses continuous historical intervals; session-aware consumers must
supply explicit schedules to the application services.

Use `MarketRepository.register` for metadata and `HistoricalIngestion.ingest` with a provider,
`CandleQuery`, `FreshnessPolicy` and injected `Clock` inside a SQLAlchemy transaction.
Only `FixtureProvider` exists now, for offline synthetic tests. No public write/import API exists.
Use `MarketReplay.replay` for trusted replay; `.inspect` exposes quality failures without filling gaps.
Apply `alembic upgrade head` to upgrade an existing database. Migrations 0002 through 0008 add market data, forecasts/outcomes, Analyze reports, watchlists, scans, portfolios and portfolio intelligence
while preserving earlier history. Applying 0008 is additive. Downgrading 0008 deletes portfolio-intelligence reports;
downgrading 0007 deletes manual portfolios and their accounting entries; downgrading 0006 deletes scan reports; downgrading 0005 deletes watchlists,
their snapshots and alert events; downgrading 0004 deletes Analyze snapshots; downgrading 0003 deletes
forecast/outcome history; downgrading to 0001 also deletes market data. Back up retained data before rollback.

## Trabalhar noutra máquina

```sh
git clone https://github.com/pixart-web/Trading-Platform.git pocket-alpha
cd pocket-alpha
```

Antes de começar a trabalhar, sincroniza a branch principal:

```sh
git switch main
git pull --ff-only
```

Cria uma branch para cada alteração e publica-a no GitHub:

```sh
git switch -c codex/nome-da-alteracao
git push -u origin codex/nome-da-alteracao
```

Nunca publiques credenciais. Usa ficheiros `.env` locais e mantém apenas um
`.env.example`, sem valores secretos, no repositório.

Faz commit e push antes de trocar de máquina;
na outra máquina faz pull da mesma branch. Bases de dados, segredos e ficheiros sem commit
não são sincronizados por Git e têm de ser provisionados separadamente.

Phase 23 persistent PAPER execution, public one-shot observation and read-only `/paper` are documented in [PAPER architecture](docs/architecture/PAPER_TRADING.md) and [completion report](docs/roadmap/PHASE_23_COMPLETION_REPORT.md). All capital and fills are simulated; live execution remains disabled.

Phase 24 versioned strategy proposals, portfolio sizing and evidence-linked lifecycle are documented in [strategy architecture](docs/architecture/STRATEGIES.md) and [completion report](docs/roadmap/PHASE_24_COMPLETION_REPORT.md). The initial family is SMA trend for spot LONG; real promotion requires matching sealed evidence and live execution remains disabled.

Phase 25 independent conditional leverage research is documented in [architecture](docs/architecture/LEVERAGE_RESEARCH.md) and [completion report](docs/roadmap/PHASE_25_COMPLETION_REPORT.md). It models isolated linear margin and explicit survival stresses only; it cannot approve orders or enable execution.

Phase 26 adds explicit local Binance Spot private GET observations and exact account-bound reconciliation; see [architecture](docs/architecture/LIVE_READ_ONLY.md) and [completion report](docs/roadmap/PHASE_26_COMPLETION_REPORT.md). Credentials are environment-only; live execution remains disabled. Authenticated real-account qualification is still unexecuted.

Phase 27 adds safety-gated spot risk, durable client-order identity, account reservations, kill latch and a narrowly allowlisted Binance Spot adapter for read-only qualification and query recovery; see [architecture](docs/architecture/SPOT_EXECUTION.md) and [report](docs/roadmap/PHASE_27_COMPLETION_REPORT.md). Only explicit synthetic qualification can dispatch; native live execution remains blocked and authenticated qualification remains unexecuted.

Phase 28 adds fail-closed Autopilot orchestration over the existing scanner, lifecycle, portfolio, risk and execution stack; see [architecture](docs/architecture/AUTOPILOT.md) and [completion report](docs/roadmap/PHASE_28_COMPLETION_REPORT.md). It is disabled by default, has no public control surface or background worker, and only explicit synthetic qualification can reach the still-authoritative Phase 27 risk boundary. Native execution remains blocked.
