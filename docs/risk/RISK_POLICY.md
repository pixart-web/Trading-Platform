# Risk policy
Risk protects capital survival and net compounding. Every eventual order must pass a fail-closed
risk decision with explicit reason codes; no score or probability can bypass it.
Required configurable checks: trade risk, position/asset/strategy/correlated/portfolio exposures,
position count, daily/weekly/monthly losses, drawdown, loss streak, spread/slippage, liquidity,
data age, strategy/broker health, cooldown and global kill switch.
Policies require approved explicit limits before live use; this foundation invents no risk thresholds.
Sizing policies (fixed fractional, volatility/ATR, parity, targeting, capped fractional Kelly) must
be researched with costs and portfolio context. Confidence never automatically implies leverage.
Leverage assessment records size, entry, stop distance, estimated liquidation distance, volatility,
modeled loss and portfolio contribution, with ACCEPTABLE/ELEVATED/HIGH_RISK/REJECTED status.
Model liquidation per instrument and venue before derivative execution.
Profit protection includes high-water mark, trailing drawdown, reserves and dynamic risk reduction.
These requirements are implemented incrementally by later phases. The current hard control remains:
live trading cannot be enabled through configuration; the native Spot adapter cannot reach dispatch.

Phase 16 portfolio accounting supplies exact manual cash, position and P&L state for later controls.
It does not implement exposure limits, sizing or risk decisions, and a recorded BUY or SELL is not an
approved order or verified fill. Live trading remains disabled.

## Phase 21 offline research

Phase 21 simulation approvals and reservations are research-only. Kill switch, stale inputs, spread, worst-case debit, exposure, daily loss and drawdown halt pending/new orders. They do not grant broker authorization or guarantee drawdown limits on existing inventory. Close marks omit intrabar stress; leverage and ruin probability remain unsupported.

## Phase 22 research factory

Phase 22 model qualification cannot approve an order or enable live configuration. Promotion policies must explicitly declare positive net return/closed-trade expectancy, samples, assets, temporal folds, drawdown and baseline improvement; synthetic/in-sample evidence cannot promote. Descriptive Monte Carlo/permutation scenarios do not estimate validated ruin risk. Registry degradation is metadata, not an implemented live suspension process.

Phase 23 applies the same research-only risk gate to incremental PAPER orders. Feed/strategy/execution health, durable idempotency and reconciliation additionally freeze new submissions. Kill/drawdown halts cancel simulated pending orders and retain genuine simulated inventory; they cannot guarantee bounded loss or authorize a live order. See ../architecture/PAPER_TRADING.md.

Phase 25 conditional leverage research adds explicit position/collateral/loss limits, stop-to-liquidation buffers and gap/volatility/slippage/funding/correlated/forced-liquidation scenarios. It cannot approve risk or execute an order. Finite scenario maxima are not guaranteed loss caps, and a ruin flag is not a ruin probability. See ../architecture/LEVERAGE_RESEARCH.md.

Phase 26 private observation requires explicit read permission and denial of every documented key write/transfer/trading flag. Unknown permissions, missing or inconsistent financial state, changing account bookends and absent/stale/unverified local expectations fail closed. MATCHED never grants execution approval; spot inventory is not leverage capacity or a P&L estimate. See ../architecture/LIVE_READ_ONLY.md.

Phase 27 implements explicit spot admission limits for capital, order/position/total exposure, inventory, daily loss, drawdown, positions, rates, freshness, spread, fee budget and kill/health. Durable unresolved orders reserve the entire account flow. These controls are qualified mechanically using a synthetic broker. The native adapter may qualify/query through GET, while REAL admission, execution authorization, configuration and transport independently block order submission. Loss limits do not liquidate existing inventory or guarantee future loss caps. See ../architecture/SPOT_EXECUTION.md.
