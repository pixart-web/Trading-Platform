# Opportunity Score architecture

Phase 12 adds a deterministic economic assessment for one directional opportunity at one forecast
horizon. It consumes an immutable Phase 8 forecast, a completed Phase 11 directional analysis,
explicit cost assumptions and causal liquidity and uncertainty evidence. It does not recompute
intelligence, create a strategy intention, approve risk or reach an execution or broker boundary.

## Input contract

An opportunity binds one market, asset, candle timeframe, horizon and as-of time. The forecast and
directional analysis must have the same identity. The engine accepts only a still-current forecast
that existed at the as-of time. A usable score also requires a calibrated forecast, exactly one LONG
or SHORT result, and available liquidity and uncertainty metrics with evidence that existed by the
as-of time.

Liquidity is a versioned ratio from zero to one where one is best. Uncertainty is a versioned ratio
from zero to one where one is most uncertain. Their source transformations are outside this module
and must be evaluated empirically. Missing context, NO_TRADE, an unavailable, expired or
uncalibrated forecast, or a forecast range with no directional downside estimate produces an
UNAVAILABLE result without partial economics or a plausible-looking score.

Costs use the existing `EconomicCostSpec`. Fees, spread, slippage and latency are expressed as
round-trip basis points and converted to a total return rate. The cost version and complete cost
input participate in the opportunity hash.

## Economic calculation

For LONG, directional expected return is forecast expected return. For SHORT, its sign is inverted.
Directional probability selects UP for LONG and DOWN for SHORT. Reward and loss are taken from the
forecast expected interval relative to zero for the selected side. Risk/reward is reward divided by
loss; a zero downside estimate fails closed because it cannot support a finite auditable ratio.

Net expected return is:

    directional expected return - round-trip fee rate - spread rate
    - slippage rate - latency rate

This is an estimate under explicit assumptions, not realized profit. Borrow, funding, taxes,
market impact beyond the supplied slippage, position size, portfolio effects, drawdown and ruin are
not modeled in this phase.

## Versioned score policy

Every policy supplies its own minimum and target values plus positive weights. The repository does
not ship promoted financial thresholds or a claim that any configuration is profitable.

Seven components are normalized to 0-100:

1. net edge between configured minimum and target net return;
2. selected calibrated directional probability between configured minimum and target;
3. expected move between configured minimum and target;
4. cost efficiency from 100 at zero cost to zero at the configured maximum cost;
5. liquidity as its supplied ratio times 100;
6. uncertainty as one minus its supplied ratio, times 100;
7. risk/reward between configured minimum and target.

Values are clipped to the component range. The final score is the Decimal weighted mean of the
seven normalized components. The output retains each raw value, normalized value, configured and
effective weight, contribution, policy hash, input hash, versions and upstream identifiers.
Opportunity Score is a ranking index and must never be displayed as a success probability.

Eligibility is separate from score availability. An available result becomes ineligible when net
return, probability, move, liquidity or risk/reward is below its configured minimum, or when cost
or uncertainty exceeds its configured maximum. Every failed gate is retained in canonical order.
This separation exposes economically weak inputs instead of hiding them as missing data.

## Ranking

The ranking service accepts one to one thousand unique scores from exactly the same horizon,
as-of time and policy hash. It ranks only available and eligible opportunities by descending score,
then descending net expected return, then UUID for a stable tie break. Unavailable and ineligible
results remain in an explicit excluded collection. An empty eligible ranking is valid.

The ranking is a same-snapshot economic comparison. Phase 15 reuses this deterministic ordering for
cross-market discovery, while separating different policy version/hash identities. The result is not a
recommendation, allocation, risk approval or order. See SCANNER.md.

## Boundaries and limitations

The implementation is an in-memory Python module with no migration, persistence, endpoint,
frontend or new dependency. All arithmetic uses Decimal and all times use UTC-aware domain values.
Models are frozen and forbid unknown fields. Tests use synthetic fixtures only and demonstrate
contract behavior, not calibration quality, statistical significance or investment performance.

Production use requires identified datasets, causal calibration and validation by asset, regime,
timeframe and horizon, sensitivity and cost stress tests, policy governance, drift monitoring,
persistence, and the later strategy, portfolio, risk and execution controls. Live execution remains
disabled.

Phase 13 consumes Opportunity Score without changing its calculation. Analyze retains each exact
score, economics, exclusions, policy/cost versions and upstream identifiers beside its forecast and
directional analysis. See ANALYZE.md.
