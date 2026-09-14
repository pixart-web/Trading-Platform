# Directional analysis architecture

Phase 11 adds a deterministic research boundary that evaluates LONG and SHORT cases independently
and emits LONG, SHORT or NO_TRADE. It sits after intelligence, forecasts and Pocket Score and before
any strategy. It does not produce a trade rank, position size, risk approval, order or broker action.

## Independent policy contract

A versioned directional policy contains exactly one LONG case and one SHORT case. Each side declares
one to sixteen uniquely identified numeric criteria. Every criterion records a human-readable label,
comparison operator, threshold and rule version. Version 1 supports inclusive greater-than-or-equal
and less-than-or-equal comparisons.

The policy has no default financial thresholds. Callers must define and validate the meaning of every
metric, rule and cutoff. LONG criteria are never inferred by negating SHORT criteria, and one side
cannot borrow a passing result from the other. Broker capabilities are absent from analysis; a spot
broker that cannot short cannot change a SHORT analytical result.

## Causal input contract

Each side supplies metrics in the exact order declared by its own policy. An available metric retains
its Decimal value, source version, UTC availability time and one or more canonical evidence
snapshots. Evidence cannot arrive after metric availability, and metric availability cannot exceed
the request as-of time. An unavailable metric has an explicit reason and no plausible value.

The request identifies market, asset, candle timeframe, forecast horizon and as-of time. Timeframe
and horizon remain distinct. Generation cannot precede as-of or exceed the injected clock. Policy
and case inputs receive deterministic SHA-256 fingerprints.

The engine intentionally accepts generic versioned metrics. It does not duplicate technical,
structure, regime, forecast or Pocket Score calculations. Adapters that turn those existing outputs
into directional metrics must preserve their identities, timestamps and evidence and require
separate empirical validation.

## Case and decision rules

Each side is evaluated in isolation:

- COMPLETE and qualifies when every declared criterion is available and passes;
- COMPLETE and does not qualify when every criterion is available and at least one fails;
- UNAVAILABLE with no qualification when any criterion is unavailable.

Every criterion result repeats its operator, threshold, rule and source versions, observed value,
pass/fail state, availability and evidence. Each case lists failed and unavailable criteria.

The final decision is a fixed fail-closed truth table:

| LONG case | SHORT case | Decision | Reason |
| --- | --- | --- | --- |
| qualifies | does not qualify | LONG | LONG_CASE_ONLY |
| does not qualify | qualifies | SHORT | SHORT_CASE_ONLY |
| qualifies | qualifies | NO_TRADE | CONFLICTING_CASES |
| does not qualify | does not qualify | NO_TRADE | NO_CASE_PASSED |
| either unavailable | any | NO_TRADE | INCOMPLETE_EVIDENCE |

No score comparison or tie between sides breaks a conflict. NO_TRADE is a complete result, not an
error or synthetic neutral forecast. The immutable result validator recomputes the truth table and
rejects a decision or reason that disagrees with its two case analyses.

## Boundaries and limitations

The module is in-memory and additive. It adds no persistence, migration, dependency, HTTP endpoint
or frontend. It does not estimate probability, confidence, expected return, costs, liquidity,
risk/reward, drawdown or ruin. The distinct, horizon-specific economic Opportunity Score is implemented by Phase 12 in
OPPORTUNITY_SCORE.md. Later strategy and risk phases remain mandatory before any order can exist.

Tests use synthetic metrics and thresholds. The repository ships no promoted directional policy,
real dataset or evidence that any criterion predicts returns. Temporal evaluation, sensitivity,
cross-asset/regime/timeframe analysis, configuration governance, persistence and drift monitoring
remain research debt. Live execution remains disabled.
