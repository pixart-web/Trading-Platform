# Scanner architecture

Phase 15 adds an explicit cross-market read model over registered market metadata and immutable Phase 13
Analyze reports. A scan discovers and filters already-produced Phase 12 Opportunity Scores. It does not
recalculate intelligence, forecasts, directional analysis or economics, and it does not create a signal,
strategy intention, allocation, risk approval or order.

## Identity and causal availability

A client supplies the scan UUID, candle timeframe, forecast horizon, UTC `as_of`, version and filters.
The service reads only Analyze reports with the exact market, timeframe and `as_of` identity. It selects
the latest stored report per market deterministically and rejects any report or opportunity generated
after the scan generation time. There is no earlier-report fallback.

The universe is built from registered assets and markets. Asset class, venue, quote currency and explicit
market identifiers are metadata filters applied before report resolution. Filter lists must be unique,
sorted and canonical. The resolved universe is bounded at 1,000 markets; excess fails closed instead of
silently truncating coverage.

Every universe market appears exactly once in the immutable report: either in one policy ranking or in
the exclusion collection. `universe_size` and `analyze_reports_found` must match those contents. Empty
universes and zero-result scans are valid and use `NO_MATCHES`.

## Economics, eligibility and comparison

A candidate must contain an available, eligible Opportunity Score for the exact requested horizon.
Optional filters cover direction, minimum score index, minimum net expected return, minimum liquidity,
maximum uncertainty, minimum risk/reward and maximum total cost. Decimal strings are retained without
client-side financial calculation. Every failed gate is recorded; upstream Opportunity Score exclusion
reasons remain attached.

Only candidates with the same Opportunity policy version and SHA-256 policy hash are comparable. The
scanner creates a separate ranking group for every policy identity and reuses the deterministic Phase 12
ordering: score, net expected return and stable Opportunity UUID tie-break. A per-policy result bound of
1–250 moves overflow candidates to the explicit `POLICY_RESULT_LIMIT` exclusion. Scores remain explained
0–100 indices, not probabilities.

## Persistence and API

Migration 0006 adds one append-only `scan_reports` table. Its JSON payload preserves the full request,
universe metadata, nested Opportunity Scores, rankings, exclusions, versions and canonical input hash.
The scan UUID is idempotent only for identical content; reusing it with another request is a conflict.
The timeframe/horizon/as-of index supports exact recent-history inspection.

The local API exposes:

- `POST /api/v1/scans` to materialize an explicit scan;
- `GET /api/v1/scans?limit=20` for bounded recent reports;
- `GET /api/v1/scans/{scan_id}` for immutable retrieval.

Responses use `no-store`; validation failures return 422, identity conflicts 409 and missing reports 404.
The Next.js gateway allowlists only scanner collection GET/POST and UUID detail GET routes, bounded query
keys, an 8 KiB body, a fixed server-only origin, redirects off and sanitized errors.

## Web experience and limits

The market workspace lets the user choose horizon, asset class, direction and economic thresholds at the
current chart timeframe and end timestamp. It renders each policy group independently with exact score,
return, liquidity, uncertainty, risk/reward and cost strings. All exclusions remain inspectable with
scanner and upstream reasons. Runtime Zod validation checks identities, hashes, Decimal strings, universe
coverage, status and ranking coherence before display.

There is no scheduler, automatic Analyze producer, background scan, notification, authentication,
authorization, rate limit or retention policy. Results depend on separately produced exact Analyze
reports and make no accuracy, calibration or profitability claim. Portfolio, strategy, risk, leverage,
execution and broker boundaries remain disconnected. Live execution stays disabled.

## Migration

Upgrade from 0005 is additive. Downgrade from 0006 removes scan reports and their index only. Watchlists,
Analyze reports, forecasts, outcomes, market data and audit history remain intact. Export retained scans
before rollback.
