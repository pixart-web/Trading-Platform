# Trading architecture
Market data → intelligence → forecasts → directional analysis → strategy → portfolio
→ sizing/risk → leverage assessment → execution → broker.
Strategies emit intentions and cannot call brokers or duplicate intelligence computations.
LONG/SHORT analyses are independent; spot capability may execute only LONG without distorting analysis.
Strategy lifecycle: RESEARCH → CANDIDATE → PAPER → SHADOW → LIVE_SMALL → LIVE, with
DEGRADED, SUSPENDED and RETIRED states. Promotions require quantitative validation; no direct live jump.
The deterministic paper broker must share the broker interface and simulate fees, spread, slippage,
latency, partial fills, precision, minimums, rejections and disconnections before live execution.
Orders require client IDs, idempotency, bounded retries, reconciliation and persisted state.
Unknown order state freezes new asset orders, queries broker, reconciles and creates an incident;
resume only after the state is known. Every order is traceable to input, strategy, risk and fills.
Live remains disabled by default and requires explicit production configuration and healthy data,
portfolio, broker, risk, reconciliation, strategy and kill switch. Foundation exposes no order route.
Withdrawals are outside trading credentials. Tests and CI cannot submit real orders.
