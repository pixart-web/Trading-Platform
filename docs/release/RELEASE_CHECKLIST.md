# Release checklist

Evidence must exist before checking an item. `PENDING` items are updated only after the final GitHub run.

- [ ] clean git status — pending final commit/push
- [x] single Alembic head — `0015`
- [ ] PostgreSQL migrations executed successfully — pending final Linux CI
- [ ] PostgreSQL integration passed — pending final Linux CI
- [ ] Redis integration passed — pending final Linux CI
- [x] Ruff passed
- [x] format passed
- [x] strict mypy passed
- [x] full local pytest passed — 1069 passed; service variants tracked separately
- [ ] skipped tests audited — local classification complete; final CI count pending
- [x] backend coverage reviewed — 91% branch coverage
- [x] frontend lint passed
- [x] frontend typecheck passed
- [x] frontend unit tests passed — 66
- [x] frontend build passed
- [x] Playwright passed — 18
- [ ] backend Docker image built — pending final Linux CI
- [ ] frontend Docker image built — pending final Linux CI
- [ ] disposable Compose environment started — pending final Linux CI
- [ ] health/readiness passed — unit/local app checks pass; container evidence pending
- [x] dependency audit completed — local Python/Node clear
- [x] secrets audit completed — baseline/hook clear
- [x] API exposure reviewed — classification in `SECURITY_REVIEW.md`
- [x] authentication boundary reviewed — Caddy whole-site auth, API internal
- [x] filesystem permissions reviewed — non-root/read-only app containers; secret modes specified
- [ ] backup/restore plan verified — plan complete; disposable CI restore pending
- [x] live trading remains disabled — `Literal[False]`
- [x] derivative execution remains disabled — `Literal[False]`
- [x] no withdrawal capability
- [x] final release documents complete
- [ ] final GitHub CI observed green
- [ ] final branch integrated into `main`

A future deployment operator must additionally verify DNS/TLS, firewall, host patch level, secret files, off-server encrypted backup target, alerts, resolved image digests and a manual rollback/restore rehearsal.
