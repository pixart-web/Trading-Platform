# Pocket Alpha

Phase 1: universal market-data domain, validated historical ingestion, PostgreSQL candle storage,
deterministic replay and a read-only API, built on the Phase 0 foundation.
No external provider is connected and no market data is seeded. No analysis or execution exists.
See [market-data architecture](docs/architecture/MARKET_DATA_ARCHITECTURE.md).

## Development

Install Python 3.12+ and Docker Compose. Create a virtual environment with
`python -m venv .venv` and activate it (`.venv\Scripts\Activate.ps1` on Windows).
Run `pip install -r requirements.lock` then `pip install --no-deps -e .`.
Start the stack with `docker compose up --build -d`. API docs: http://localhost:8000/docs.
Probes: `/health/live` and `/health/ready`. Compose runs migrations before the API starts.
For host development, start `docker compose up -d db redis`, copy `.env.example` to `.env`,
run `alembic upgrade head`, then `uvicorn pocket_alpha.main:app --no-access-log`.
Sample credentials and loopback bindings are for local development, not production deployment.

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
Apply `alembic upgrade head` to upgrade an existing Phase 0 database. Migration 0002 adds market
tables and preserves audit history. Downgrading to 0001 deletes market data; back up before rollback.

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
