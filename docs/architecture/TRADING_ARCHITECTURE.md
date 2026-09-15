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

Phase 11 implements only the directional-analysis boundary. Versioned LONG and SHORT criteria are
evaluated independently, and a fixed truth table returns NO_TRADE for conflict, no passing case or
incomplete evidence. Broker capability cannot alter analysis. This output is not a strategy
intention or risk approval and cannot reach execution. See DIRECTIONAL_ANALYSIS.md.


Phase 12 implements only the economic opportunity assessment associated with a completed LONG or
SHORT analysis. It subtracts explicit round-trip costs, explains every score component and excludes
results that fail configured economic gates. It does not emit a strategy intention, size capital,
approve risk or authorize an order. See OPPORTUNITY_SCORE.md.

Phase 13 presents forecasts, independent LONG/SHORT cases and opportunity economics through one
shared immutable Analyze report. Its ELIGIBLE or INELIGIBLE labels only restate configured Phase 12
gates. They are not trade recommendations, position sizing or risk approval and cannot authorize an
order. See ANALYZE.md.

Phase 14 watchlists organize markets and record changes in stored Analyze conclusions. A member,
snapshot or alert event is not a strategy intention, portfolio decision or risk approval and has no
path to execution or a broker. See WATCHLISTS.md.

Phase 15 ranks eligible stored Opportunity Scores only within an identical policy version and hash. A
scan remains a discovery read model and cannot emit a strategy intention, allocate capital, approve risk
or reach execution or a broker. See SCANNER.md.

Phase 16 implements the portfolio accounting boundary for manually supplied deposits, withdrawals,
buys and sells. These immutable records describe user-entered accounting facts and are not fills or
orders. The portfolio can inform later risk work, but this phase performs no allocation, sizing, risk
approval, leverage assessment, execution or broker action. See PORTFOLIO.md.
