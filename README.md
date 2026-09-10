# Pocket Alpha

Phase 0 foundation: FastAPI, typed domain, PostgreSQL audit, Redis readiness, Docker and CI.
No market analysis or execution is implemented yet. See docs/roadmap/GAP_ANALYSIS.md.

## Development

Install Python 3.12+ and Docker Compose. Create a virtual environment with
`python -m venv .venv` and activate it (`.venv\Scripts\Activate.ps1` on Windows).
Run `pip install -r requirements.lock` then `pip install --no-deps -e .`.
Start the stack with `docker compose up --build -d`. API docs: http://localhost:8000/docs.
Probes: `/health/live` and `/health/ready`. Compose runs migrations before the API starts.
For host development, start `docker compose up -d db redis`, copy `.env.example` to `.env`,
run `alembic upgrade head`, then `uvicorn pocket_alpha.main:app --no-access-log`.
Sample credentials and loopback bindings are for local development, not production deployment.

Checks: `ruff check .`, `ruff format --check .`, `mypy`,
`pytest --cov=pocket_alpha --cov-report=term-missing`.
Integration requires PostgreSQL and Redis and `PA_INTEGRATION=1` (enabled in CI).
Use a disposable database: the integration test downgrades and deletes its audit history.
Never run this integration test against retained data.

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
