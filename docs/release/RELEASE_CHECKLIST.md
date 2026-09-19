# Release checklist

Evidence exists in green GitHub Actions run 35438637940. Main integration is checked only after it occurs.

- [x] clean git status — verified before the evidence commit
- [x] single Alembic head — `0015`
- [x] PostgreSQL migrations executed successfully
- [x] PostgreSQL integration passed
- [x] Redis integration passed
- [x] Ruff passed
- [x] format passed
- [x] strict mypy passed
- [x] full local pytest passed — 1069 passed; service variants tracked separately
- [x] skipped tests audited — CI: 1299 passed, 1 intentional SQLite-only skip
- [x] backend coverage reviewed — 91% branch coverage
- [x] frontend lint passed
- [x] frontend typecheck passed
- [x] frontend unit tests passed — 66
- [x] frontend build passed
- [x] Playwright passed — 18
- [x] backend Docker image built
- [x] frontend Docker image built
- [x] disposable Compose environment started
- [x] health/readiness passed
- [x] dependency audit completed — local Python/Node clear
- [x] secrets audit completed — baseline/hook clear
- [x] API exposure reviewed — classification in `SECURITY_REVIEW.md`
- [x] authentication boundary reviewed — Caddy whole-site auth, API internal
- [x] filesystem permissions reviewed — non-root/read-only app containers; secret modes specified
- [x] backup/restore plan verified — disposable PostgreSQL restore passed
- [x] live trading remains disabled — `Literal[False]`
- [x] derivative execution remains disabled — `Literal[False]`
- [x] no withdrawal capability
- [x] final release documents complete
- [x] final candidate GitHub CI observed green — run 35438637940
- [ ] final branch integrated into `main`

A future deployment operator must additionally verify DNS/TLS, firewall, host patch level, secret files, off-server encrypted backup target, alerts, resolved image digests and a manual rollback/restore rehearsal.
