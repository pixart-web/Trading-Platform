# Phase 16 — portfolio accounting

Phase 16 adds persistent manual portfolios after the strategy boundary and before risk, leverage,
execution and brokers. It records accounting facts supplied by the user. It does not create strategy
intentions, size positions, approve risk, place orders, import broker activity or claim that a
manual entry was filled in a market.

## Contracts and persistence

A portfolio has a client-supplied UUID, trimmed name, canonical base currency, fixed
`MOVING_AVERAGE_V1` accounting method, valuation candle timeframe and optimistic revision.
Migration 0007 adds `portfolios` and the append-only `portfolio_entries` ledger. Each entry has
a client-supplied UUID, monotonically increasing sequence, occurrence and recording timestamps,
exact stored inputs, derived gross value and cash effect, and an immutable canonical payload.

The accepted entry types are `DEPOSIT`, `WITHDRAWAL`, `BUY` and `SELL`. Cash entries have
one positive amount and no fee or market. Trades have one registered market, positive quantity and
price, and a non-negative fee. Markets must quote in the portfolio base currency because no FX
source or conversion policy exists. A stale revision, negative resulting cash, oversell, future
entry, out-of-order occurrence time or conflicting reused UUID fails closed.

The ledger is bounded at 10,000 entries and 250 distinct markets per portfolio. Listing is bounded
and ordered. Repeating the same portfolio or entry UUID with identical content is idempotent;
different content is a conflict. Entries cannot be edited or deleted through the API.

All monetary arithmetic uses Python `Decimal`, stored as `NUMERIC(38,18)`, and is quantized to
18 decimal places with round-half-even. Buy fees increase cost basis. Sell fees reduce proceeds and
realized P&L. A partial sale retains the moving average cost of the remaining quantity. A fully
closed position retains realized P&L while current cost and valuation become zero/unavailable.

## Causal snapshots

`GET /api/v1/portfolios/{id}/snapshot?as_of=...` rebuilds the ledger from entries whose occurrence
and recording timestamps are both at or before the requested UTC cutoff. This prevents a late
backfill from appearing in an earlier view. The snapshot uses only the latest stored close in the
portfolio valuation timeframe whose close and receipt times are no later than the cutoff.

A snapshot exposes cash, net contributions, fees, realized P&L, positions, cost basis, market value,
unrealized P&L and equity. If any open position lacks an eligible price, that position remains
explicitly unvalued and the portfolio status is `PARTIAL`; aggregate market value, unrealized P&L
and equity are omitted instead of being fabricated. Closed positions do not require a price.
Canonical input identity is retained through the portfolio revision, ledger sequence and SHA-256
fingerprint.

## HTTP and web experience

The FastAPI routes create and list portfolios, read one portfolio, append/list entries and build an
as-of snapshot. Responses disable caching and use 404 for missing identities, 409 for conflicts or
stale revisions, and 422 for invalid accounting operations.

The existing Next.js server gateway allowlists only these portfolio paths, methods and query keys.
The responsive portfolio panel creates a manual portfolio, displays backend-calculated exact values,
records manual entries and exposes the immutable ledger. The browser validates identities, revisions,
Decimal strings, structural totals and valuation completeness; it does not recalculate financial
amounts. Manual records are labelled as neither orders, recommendations nor risk approvals.

## Limits and later work

Phase 16 supports one base currency, long manual positions and moving-average accounting. It does
not implement FX, short positions, tax lots, dividends, splits, transfers, reversals, broker imports,
authentication, ownership, allocation, concentration, correlations, portfolio risk, orders or
reconciliation. Portfolio intelligence is implemented separately in Phase 17.

Phase 17 consumes the immutable accounting snapshot through a separate portfolio-intelligence
boundary. It cannot mutate the ledger and does not turn an observation into an allocation, risk approval
or order. See PORTFOLIO_INTELLIGENCE.md.
