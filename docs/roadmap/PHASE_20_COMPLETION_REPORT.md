# Phase 20 completion report

## Summary, phase and status

Phase 20 implements shared causal news/sentiment/macro context and the real public market-data gate.
Native feeds are read-only Coinbase Exchange spot candles and official Federal Reserve RSS metadata.
Normalized numeric sentiment/macro ports preserve provenance, units and versions; no guessed numeric
feed or sentiment model is enabled. Implementation is complete for this documented scope. Production
service integration and profitability are not claimed. Phase 21 is next and has not been started.

## Assessment, gaps, debt, design and acceptance

The clean baseline was Phase 19 commit 784d925. Existing derivative/fundamental/accounting/forecast
boundaries were preserved. The baseline lacked contextual persistence and a native historical price
adapter; synthetic-only serious economic research could not satisfy the real-data gate. Known debt
included absent native numeric macro/sentiment/derivative feeds and unavailable local PostgreSQL/Redis
integration. Phase 20 does not conceal or resolve that infrastructure debt.

Before production edits, the assessment declared causal context history, public Coinbase candles,
Fed title/link metadata, explicit real/synthetic datasets, additive migration 0011, read-only endpoints,
bounded transport and failure/availability/replay acceptance. No event published/available/ingested
later may enter an earlier cutoff; no ambiguous units, invented sentiment, fake fallback or mixed
sources may become trusted data. Invalid paginated batches must leave no partial writes. Reimports
preserve first knowledge times; revisions must preserve identity and historical causality. REAL
imports must map native product to crypto asset, venue and quote and replay identically after reload.
These documented acceptance checks passed in unit/isolated storage tests and actual public smoke.

## Architecture and security boundary

The Python modular monolith adds one context kernel reused through a GET-only API, a normalized
provider port, immutable observation history and context-snapshot-1.0.0 hashes. Data ordering remains
market data → intelligence → forecasts → directional analysis → strategy → portfolio → risk → leverage
assessment → execution → broker. No strategy, risk permission, leverage instruction, execution,
broker dependency, live activation or automatic forecast recomputation is introduced.

Context publication, availability and ingestion are separate UTC timestamps. News may represent a
known SCHEDULED future event explicitly; it cannot masquerade as observed numeric data. Sentiment is
a finite Decimal [-1,1] score with method version, not probability/confidence. Macro requires explicit
units, currency where monetary, and causal reporting periods. Revision chains preserve source,
entity, event, units/currency/period and temporal ordering. PostgreSQL entity locking is specified;
failed batches use a savepoint. Snapshots filter all knowledge times, choose latest available revision
per source/event and verify hashes independent of generation time. Coverage means presence, not
freshness or permission to trade. Historical identity/security-master membership is not implemented.

The unauthenticated public transport uses verified HTTPS GET, bounded timeout/bytes/attempts,
request spacing, rate-limit handling, bounded backoff and Retry-After. Redirected responses must keep
HTTPS origin. Error streams close; raw bodies and secrets are not logged. XML DTD/entities and
non-primary news links are rejected. No API write/import/order route or startup import exists.
Live settings remain Literal[False]; no credentials, withdrawals, real orders, deployment or DNS
changes occur. Local REAL evidence is git-ignored and never bundled as synthetic test data.

market-dataset-1.0.0 freezes explicit REAL/SYNTHETIC origin, source/product mapping, asset/market/venue/
quote identity, query/timeframe, capture and exact candles with SHA-256 verification. Stored replay
releases bars conservatively at dataset capture. Downloaded past prices never receive fabricated
past local availability. Hashes detect accidental payload changes, not adversarial database rewrites.
The registry accepts immutable frozen datasets only; there is no application update/delete method.

## Complete changed file list

- .gitignore
- docs/architecture/CONTEXTUAL_INTELLIGENCE.md
- docs/architecture/MARKET_DATA_ARCHITECTURE.md
- docs/architecture/REAL_MARKET_DATA.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/research/VALIDATION_POLICY.md
- docs/roadmap/PHASE_20_COMPLETION_REPORT.md
- docs/roadmap/ROADMAP.md
- migrations/env.py
- migrations/versions/0011_context_and_datasets.py
- src/pocket_alpha/common/public_http.py
- src/pocket_alpha/contextual/__init__.py
- src/pocket_alpha/contextual/api.py
- src/pocket_alpha/contextual/models.py
- src/pocket_alpha/contextual/providers.py
- src/pocket_alpha/contextual/service.py
- src/pocket_alpha/contextual/storage.py
- src/pocket_alpha/main.py
- src/pocket_alpha/market_data/coinbase.py
- src/pocket_alpha/market_data/datasets.py
- src/pocket_alpha/market_data/import_public.py
- src/pocket_alpha/market_data/smoke_public.py
- tests/test_phase20_api.py
- tests/test_phase20_context.py
- tests/test_phase20_http.py
- tests/test_phase20_migration.py
- tests/test_phase20_public_data.py

## Migration and migration risks

0011 follows 0010 and adds context_entities, context_mappings, context_observations and
market_data_datasets. Mapping/source-record/event-revision uniqueness, asset/entity/mapping/self
foreign keys, publication/availability/ingestion ordering and revision/supersession constraints are
additive. Existing candle, portfolio, fundamental, derivative and forecast tables are unchanged.
Decimal values are exact JSON strings; SQLite is used only for isolated tests/evidence. Upgrade is
additive. Downgrade deletes these context histories/datasets: export/backup before rollback. SQL
PostgreSQL generation and isolated SQLite upgrade/constraints/downgrade passed. Real PostgreSQL
upgrade, locking and rollback execution are not locally verified.

## Commands, exact tests and results

Final checks used .venv/Scripts/python.exe and .venv/Scripts/ruff.exe:

- ruff check . — passed.
- ruff format --check . — passed, 214 files already formatted.
- python -m mypy — passed, 146 source files.
- python -m pytest -q — 544 passed, 159 skipped, 2 warnings in 25.30s.
- python -m pytest tests/test_phase20_context.py tests/test_phase20_public_data.py
  tests/test_phase20_http.py tests/test_phase20_api.py tests/test_phase20_migration.py
  --cov=pocket_alpha.contextual --cov=pocket_alpha.common.public_http
  --cov=pocket_alpha.market_data.coinbase --cov=pocket_alpha.market_data.datasets
  --cov-report=term-missing -q — 26 passed, 8 skipped, 2 warnings in 3.95s;
  94% combined coverage, 532 statements/33 uncovered. HTTP transport and API coverage are 100%.
- python -m pytest tests/test_phase20_migration.py -q — 1 passed in 0.14s.
- python -m alembic heads — 0011 (head).
- python -m alembic upgrade head --sql — PostgreSQL SQL generated through 0011.
- python -m alembic downgrade 0011:0010 --sql — rollback SQL generated.
- python -m pocket_alpha.market_data.smoke_public --public-read — actual public GETs,
  isolated storage commit/reload and deterministic dataset/news verification passed.
- Final MarketDataset.model_validate_json of persisted REAL evidence — passed with final schema,
  24 replay events and unchanged content hash.
- git diff --check — passed. git check-ignore data/local — confirmed exclusion.

All automated HTTP fixtures are explicitly synthetic and perform no public network or real orders.
New tests cover causal cutoffs, publication/ingestion delay, explicit revisions, immutability/hash
corruption, units/periods, future/scheduled events, atomic failures, provider budgets/cycles, native
UTC pagination, exact decimals, gaps/mixed sources, economic mapping, unavailable context, GET-only
API, generic storage errors, bounded retries/rate embargo, stream closing and HTTPS-origin redirects.

The 159 skips are service integration cases not enabled/configured locally, including 8 new cases.
PostgreSQL/Redis readiness, PostgreSQL concurrent writer behavior, real migration execution, Docker
image builds and GitHub CI for these unpublished commits were not executed in this task. Phase 19
recorded Windows Application Control blocking the local psycopg binary driver and an unavailable
Docker Linux daemon; no production-ready claim follows from isolated SQLite. Frontend checks were
not rerun because no frontend files changed. Two existing Starlette/httpx/AnyIO deprecation warnings
remain; valid tests were not weakened and no new dependency was added.

## Real-data evidence and provenance

The successful final public smoke retrieved BTC-USD 1h bars for
2025-01-01T00:00:00+00:00 through 2025-01-02T00:00:00+00:00 (end exclusive):

- Origin REAL; source coinbase-exchange; instrument BTC-USD; 24 validated native candles.
- Dataset ID 2c1d135b-27e1-4405-8504-b157c769ffc4.
- Capture 2026-09-17T20:30:49.403651+00:00.
- Content hash 79c7606a172478a6ac7cd94a0204685c30bf992b373e0be0a0f89b72058c5f44.
- Stored replay equality true after commit and a new storage session.
- Source federal-reserve-rss; 20 official news metadata observations imported.
- News cutoff 2026-09-17T20:30:49.659450+00:00.
- Context hash bd6d8f1ac03e7c0e9e29efda99ef1bac08da92af3649ab13451fcba3a5c62753.
- Stored context equality true, with no invented numeric sentiment or macro values.

Raw dataset, unique isolated SQLite file and evidence JSON are under ignored data/local; only the
manifest evidence is documented here. Sources and vendor semantics are linked in
[real-data architecture](../architecture/REAL_MARKET_DATA.md) and
[context architecture](../architecture/CONTEXTUAL_INTELLIGENCE.md).

## Financial coverage and economic assumptions

Empirical coverage is one public crypto spot market/day and current Fed RSS metadata, not a universal
market-data catalogue or economic validation sample. Normalized contracts support explicit sentiment
and macro contexts; numeric vendor feeds/models remain unavailable. Coinbase prices/volume retain
native quote/base units, Decimal and UTC; unavailable buckets remain gaps. No forward filling,
resampling, synthetic spreads, fabricated liquidity/fills, profit/probability/confidence or FX estimate
is introduced. Fixed UTC candle duration and conservative capture availability are engineering
conventions. This data gate proves legitimate inputs and deterministic storage, not sustainable net
compounded growth, drawdown/ruin compliance, calibration, profitability or a causal as-traded 2025
strategy. Cost-aware economic evaluation remains required before any strategy promotion.

## Limitations, debt and next phase

Outstanding work includes PostgreSQL/Redis integration and writer locking, streaming availability,
provider correction policy, security-master/survivorship and corporate actions, native numeric
macro/sentiment/stock/index/commodity/derivative feeds, provider/model calibration, text relevance/NLP,
economic recency policies and frontend/Analyze consumers. Native public HTTP limits are per client;
multiple processes may still encounter rate limits. Bounded history/snapshot sizes fail explicitly.
Publisher changes without explicit source-record revisions reject rather than silently rewriting.
Two dependency deprecations remain recorded. No empirical profitability or statistical confidence
claim is made. No production readiness or release certification is granted.

A phase-specific local commit follows the authorized master plan. No push or main integration is
performed here; the master plan reserves final publication for later completed phases/audits.
Next phase: 21 — event-driven backtesting. It has not been started.
