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

Phase 17 observes portfolio accounting state and historical market relationships. Its allocations,
concentrations, volatility, beta, correlations and risk contributions are descriptive inputs for later
risk work. They cannot approve risk, size capital or authorize execution. See
PORTFOLIO_INTELLIGENCE.md.

## Phase 21 offline research

Offline Phase 21 research preserves the data -> shared intelligence -> forecast inputs -> strategy intent -> portfolio -> risk -> simulated execution boundary. Spot LONG inventory only is supported; unsupported leverage/SHORT routes cannot execute. Strategy callbacks receive causal immutable views. See [BACKTESTING.md](BACKTESTING.md) for receipt and complete-bar-close assumptions.

## Phase 22 research factory

Phase 22 research states qualify model evidence only. CHALLENGER requires real OOS net economics; SHADOW additionally requires frozen one-shot holdout evidence. PRODUCTION entry remains disabled. No state is risk approval, broker authorization or actual shadow/live operation. Strategy lifecycle/paper execution remains future work; see [RESEARCH_FACTORY.md](RESEARCH_FACTORY.md).

Phase 23 PAPER uses the existing strategy intention/risk/execution interfaces with durable checkpoints and shared simulated fills. Local disconnection suspends until explicit fresh accounting reconciliation. No real broker is implemented; all capital/execution remains PAPER. See [PAPER_TRADING.md](PAPER_TRADING.md).

Phase 25 evaluates leverage only in offline research after an explicitly bound caller portfolio/prior-risk context. Results are not approvals and cannot enter spot/PAPER/execution routes. Conditional liquidation, deficits and survival stresses are documented in [LEVERAGE_RESEARCH.md](LEVERAGE_RESEARCH.md).

Phase 26 observes private Binance Spot account identity, balances/spot inventory, open orders, scoped trade history and instrument metadata. Exact local reconciliation and key-scope guards can only establish read-only readiness; they cannot approve orders or enable live trading. No strategy imports the adapter. See [LIVE_READ_ONLY.md](LIVE_READ_ONLY.md).
