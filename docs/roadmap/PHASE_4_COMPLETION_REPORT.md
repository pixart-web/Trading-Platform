# Phase 4 — Market structure

## Summary, assessment and design

User authorized Phase 4. Initial tree was clean at 23c394c, with Phases 0–3 implemented. Before
production edits the task reported the assessment, missing structure module, existing data/provider
and validation debt, proposed versioned backend design, expected files, no migration risk and
acceptance criteria. Existing work was preserved.

Added shared MarketStructure over trusted replay: confirmed strict pivots, FIRST/HH/HL/LH/LL/EQUAL,
close-cross INITIAL_BREAK/BOS/CHOCH, state and reason evidence, consumed-level tracking, explicit
confirmation/availability times, frozen snapshots and prefix provenance. Technical canonical candle
encoding was extracted without changing its contract so both analytical modules use one helper.
See ../architecture/MARKET_STRUCTURE.md for the exact convention and state transitions.

## Complete file list

Created:

- src/pocket_alpha/intelligence/provenance.py
- src/pocket_alpha/intelligence/structure/__init__.py
- src/pocket_alpha/intelligence/structure/models.py
- src/pocket_alpha/intelligence/structure/service.py
- tests/test_market_structure.py
- docs/architecture/MARKET_STRUCTURE.md
- docs/roadmap/PHASE_4_COMPLETION_REPORT.md

Modified:

- src/pocket_alpha/intelligence/technical/service.py
- README.md
- docs/architecture/INTELLIGENCE_ARCHITECTURE.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md

No database migrations, dependencies, API routes, frontend or CI configuration changes.

## Verification and acceptance

Tests cover mirrored reference BOS/CHOCH/reversal paths, continuation after a failed reversal,
HH/HL/LH/LL evidence, paired trend establishment without breaks, mixed/opposite states, strict ties,
dual outside-bar pivots, wick/touch exclusion, one-time level consumption, subtick Decimal prices,
all-prefix and future-perturbation invariance across five window configurations, malformed specs,
immutable serialization, shared technical/structure hashes, ambient precision independence, delayed
data, explicit session counts, missing/stale/future rejection and empty closed sessions.

Targeted run: 31 passed, 4 skipped (PostgreSQL unavailable locally); structure 100% statement and
branch coverage (180 statements, 40 branches).
Final local full suite: 241 passed, 44 skipped, 2 upstream deprecation warnings; overall statement
coverage 99% (1154 statements, 4 missed). Ruff lint passed, format checked 68 files, and strict mypy
passed on 46 source files. PostgreSQL/Redis skips and remote CI results are verified separately.

Commands: python -m ruff check .; python -m ruff format --check .; python -m mypy .;
python -m pytest --cov=pocket_alpha --cov-report=term-missing;
python -m pytest tests/test_market_structure.py --cov=pocket_alpha.intelligence.structure
--cov-branch --cov-report=term-missing -q.

Initial checks found formatting/type issues, which were corrected. One wick test fixture accidentally
had equal highs and therefore did not confirm its intended strict pivot; its OHLC input was corrected,
preserving the no-break assertions. No valid assertion was removed or weakened.

## Financial coverage, security, limitations and debt

Synthetic fixtures only, never application data. Numerical/event regression and high code coverage
do not establish predictive value, profitability or economic safety. No net returns, costs, fills,
probabilities, scores, signals or financial recommendations were calculated. BOS/CHOCH are the
documented model's labels, not guarantees about future direction. No intrabar path is inferred.

No secrets, external credentials, public routes, broker calls or live trading. The hard prohibition
on enabling live execution is unchanged. Data/dependency failures propagate. Historical freshness
policy remains explicit; late observations cannot be retrospectively treated as known.

No real provider, persistent structure snapshots, UI/API overlays, incremental stream/restart state,
protected/nested swings, calendar inference or corporate-action adjustments. The query start is
part of analytical context. Authentication, observability and existing dependency warnings remain
debt. Local Docker/service integration and frontend regressions run remotely in existing CI;
the frontend is unchanged. No economic validation on real market data is claimed.

Next phase: 5 — support/resistance zones and chart overlays. Not started.
