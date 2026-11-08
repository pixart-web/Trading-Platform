# Manual operational PAPER flow

1. Launch Local workspace and fetch actual public market metadata/candles.
2. Create a new virtual EUR experiment (suggested1000 EUR). No synthetic account or market fixture is inserted into operational mode.
3. View authoritative cash, available/reserved cash, inventory, basis, realized/unrealized P&L, fees and marked equity. Mark time is shown separately; historical valuation is not a live exchange quote.
4. A manual BUY/SELL request passes the qualified one-order risk gate before entering the journal. The current immutable profile assumes10bps fees,10bps spread,5bps slippage and5bps impact, a100 EUR order cap,10% exposure,3% daily loss and10% drawdown. These are explicit simulation assumptions, not observed exchange costs or validated profitability settings.
5. Explicit processing of a newly observed eligible closed bar can simulate a fill. It requires a verified connection, freshness near the close, causal eligibility and an order created in the current uninterrupted process session. Old/recovered orders are not automatically resubmitted or filled. Stale/gap/disconnected inputs are not invented.
6. Emergency stop cancels pending simulation and freezes the experiment while preserving genuine simulated inventory/history. Reset means create a new experiment, never erase old journals.

One market/position and one outstanding order per experiment remain the supported financial scope. Multi-market shared cash, configurable strategies/risk forms, UTC day rollover and automatic resume are not implemented. Day-boundary processing fails closed; retain the old account and create a separate experiment rather than rewriting its history. Historical orders may therefore remain unresolved until explicitly stopped.

The local pipeline presently reaches data quality → qualified SMA/EMA → manual decision → risk → PAPER simulation → durable journal → actual application presentation. It does not qualify a native automated strategy, market structure, forecast or directional engine. Real-data simulated fills must be observed forward in time; deterministic fixtures separately prove mechanics and are never labelled actual performance.
