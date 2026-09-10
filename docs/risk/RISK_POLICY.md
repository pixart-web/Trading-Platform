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
These are requirements for later phases, not implemented risk controls. Current hard control:
live trading cannot be enabled through configuration and no execution adapter exists.
