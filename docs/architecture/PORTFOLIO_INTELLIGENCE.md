# Phase 17 — portfolio intelligence

Phase 17 creates immutable, explainable intelligence snapshots over the exact Phase 16 accounting
state. It observes allocation and market risk. It does not recommend a trade, allocate capital,
approve risk, create an order or connect to a broker.

## Identity and causality

Every report has a client UUID, portfolio revision, ledger sequence, UTC as-of, valuation timeframe,
versioned policy and policy hash. The input hash covers the complete causal portfolio snapshot,
policy, optional benchmark identity and exact candle points used. Reusing the UUID with identical
request identity returns the stored report; changed identity is rejected.

The service obtains the portfolio through the Phase 16 snapshot contract. Return series contain only
stored candles in the portfolio timeframe whose close and receipt timestamps are no later than the
requested cutoff. The window is bounded by policy. Late observations cannot alter a historical
report. Migration 0008 stores append-only report payloads and lookup metadata.

## Available calculations

When the portfolio has a complete valuation, allocation is grouped by market, asset class, currency,
venue, direction and cash. Portfolio weights use total equity. Concentration uses the invested sleeve:
HHI, largest bucket weight and inverse HHI are reported separately for market, asset class, currency
and venue. Inverse HHI is an effective concentration count, not an asset count or proof of
diversification.

Sample volatility uses non-annualized close-to-close returns. Correlations require aligned returns and
nonzero variance. Beta requires an explicit registered benchmark and sufficient aligned observations.
Portfolio volatility applies current market-value/equity weights to the aligned return window. Euler
variance contributions explain how each market contributes under those same current weights; negative
contributions are possible. These historical diagnostics are neither forecasts nor probabilities.

The policy defaults to 60 bars, 20 minimum observations and a maximum valuation-price age of three
bars. Defaults are engineering availability rules and have not been economically calibrated. The
report preserves the policy so later versions cannot silently change historical meaning.

## Explicit unavailable state

The current asset model has no versioned sector taxonomy. Stored candles do not establish executable
liquidity or capacity. Phase 16 has no causal NAV series for drawdown, and manual entries do not carry
immutable regime or forecast-horizon attribution. Sector concentration, liquidity, drawdown, regime
exposure and horizon exposure therefore return explicit unavailable reasons.

Incomplete portfolio valuation suppresses allocation and portfolio-risk calculations. Insufficient
or zero-variance return history suppresses affected volatility, correlation, beta and contribution
metrics. Stale valuation prices produce a warning observation. No missing value becomes zero.

## API and web

Nested portfolio routes list and create intelligence reports; a separate read route fetches one report.
Requests and pagination are bounded, responses are not cached, and immutable identity conflicts return
409. The Next.js gateway allowlists only these paths and methods.

The Portfolio workspace can record an analysis and display exact allocation plus available and
unavailable diagnostics. The browser validates report identity, canonical ordering, metric state and
hashes. It does not recalculate financial metrics.

## Limits

The current-weight historical risk model is descriptive and does not reconstruct historical holdings.
It does not estimate transaction costs, tail risk, VaR, expected shortfall, capacity, future volatility,
ruin, or economic edge. No sector, liquidity, NAV, regime or horizon source was fabricated. Phase 18
fundamentals is not started by this phase.
