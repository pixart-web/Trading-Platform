# Analyze architecture

Phase 13 delivers the shared Analyze experience over the existing intelligence, forecast, scoring,
directional and opportunity boundaries. It assembles and displays immutable artifacts; it does not
recompute them, turn scores into probabilities, create recommendations, emit strategy intentions or
approve risk. The same report contract can serve a human-facing read model and later authorized
application consumers without creating another intelligence implementation.

## Snapshot contract

One report is bound to a market, asset, candle timeframe, UTC as-of time and report version. It
contains one setup-level Pocket Score slot and exactly the thirteen supported forecast horizons in
canonical order from 1H through 12M. Candle timeframe remains distinct from every forecast horizon.

Each horizon has one explicit slot for its immutable forecast, directional analysis and Opportunity
Score. Every slot contains either the complete artifact or an unavailable reason, never both and
never an unexplained null. An Opportunity Score can appear only beside the exact forecast and
directional identifiers that it references. Forecast, analysis and opportunity identifiers must be
unique across horizons.

The assembler verifies market, asset, timeframe, horizon and as-of identity. Forecasts must have
existed at the report as-of time. Pocket Score, directional analysis and opportunity generation must
precede report generation. The report cannot use a future as-of or generation time. The input hash
covers every nested artifact and explicit absence reason using the shared canonical encoder.

## Coverage and conclusions

Report and horizon coverage use COMPLETE, PARTIAL and UNAVAILABLE. These statuses describe artifact
presence, not analytical quality or trade eligibility. A completed pipeline may legitimately expose
an unavailable forecast, NO_TRADE or an ineligible opportunity.

Every horizon derives one presentation conclusion:

- ELIGIBLE_LONG or ELIGIBLE_SHORT when its Opportunity Score is available and eligible;
- INELIGIBLE_LONG or INELIGIBLE_SHORT when economics were calculated but configured gates failed;
- NO_TRADE when the independent directional analysis has no unique qualifying side;
- UNAVAILABLE when no defensible directional/economic conclusion exists.

Canonical issues expose missing, unavailable, expired or uncalibrated forecasts; missing or
NO_TRADE directional analysis; and missing, unavailable or ineligible opportunities. Pocket Score
absence or unavailability remains a separate report-level issue. The complete upstream artifacts
retain probabilities, expected ranges, LONG and SHORT criteria, evidence, opposition, uncertainty,
economic assumptions, exclusion reasons and versions.

These conclusions are structured summaries of existing artifacts. They are not recommendations,
portfolio decisions or risk approvals.

## Persistence and API

Migration 0004 adds `analyze_reports`, an append-only JSON snapshot table keyed by report UUID and
indexed by market, candle timeframe and as-of time. Indexed columns retain identity, status,
version, generation and input hash; the payload retains the full validated report. Re-appending the
same report is idempotent, while different content under one UUID raises a conflict. The application
ledger rejects future-generated reports.

`GET /api/v1/markets/{market_id}/analysis?timeframe=1h&as_of=<UTC>` performs an exact snapshot lookup.
It never falls back to an older report that could appear current. A known market without that exact
snapshot returns HTTP 200 with UNAVAILABLE and `NO_ANALYSIS_SNAPSHOT`; an unknown market returns
404, and naive or future times return 422. The endpoint is read-only and disables caching.

The Next.js gateway allowlists only this route and the `timeframe` and `as_of` query keys in addition
to existing market-data routes. It continues to block arbitrary paths, origins, credentials,
redirects and unbounded client parameters.

## User experience

The existing market workspace requests Analyze for the selected market, timeframe and chart-end UTC
time. Runtime Zod validation checks the response envelope, all thirteen horizons, report and nested
artifact identities, upstream links, timestamps, Decimal strings and hashes before display.

A stored report shows Pocket Score, coverage, every horizon conclusion, selected calibrated
probability, expected and net returns, Opportunity Score, uncertainty, economic exclusions, both
LONG and SHORT criterion cases and their versions. Exact Decimal strings are retained. Missing
snapshots and failed requests use distinct accessible states. Responsive layouts preserve the same
content on small screens. The interface labels scores as indices and explicitly states that they are
not probabilities or risk approvals.

No synthetic analysis ships in production. Browser and backend fixtures are test-only.

## Migration and operational limits

Upgrade from 0003 is additive and preserves existing data. Downgrade from 0004 deletes all Analyze
snapshots while leaving forecasts, outcomes, market data and audit history intact; export retained
reports before rollback.

There is no scheduled producer, provider adapter, promoted policy or real research artifact in this
phase. Reports must be assembled and published by an authorized internal application path from
legitimate upstream artifacts. An empty installation therefore displays honest unavailability.

Future work includes production orchestration, configuration governance, freshness policy by use
case, persistence for intermediate score and directional artifacts, authorization, rate limiting, production watchlist/scan orchestration, and temporal economic validation. Strategy, portfolio, risk, leverage,
execution and broker boundaries remain disconnected. Live execution stays disabled.
