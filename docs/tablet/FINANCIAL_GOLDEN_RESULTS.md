# Financial golden validation

Oracle: existing Python `backtesting.risk.authorize/halt`, `simulation.engine.SimulatedExecution`, technical service `_calculate` (50-digit HALF_EVEN policy) and decimal.Context(prec=80, ROUND_HALF_EVEN). Those production engines are unchanged. `tests/local_kernel_vectors.py` invokes them and emits version-controlled synthetic fixture JSON to JVM resources and instrumentation assets. CI reruns generation in check-only mode; changed oracle outputs require explicit review. Never use this synthetic set as economic or profitability evidence.

Coverage in this bounded foundation:

- Three exact decimal vectors: repeating division and even/odd 80-digit HALF_EVEN ties.
- SMA/EMA, period3, ten observations each: warmup/status/reason and exact values; explicit cutoff, future and unordered input rejection.
- Ten admission vectors: approval, kill, stale data, quantity/step, minimum/order notional, spread, exposure, cash and unsupported short behavior.
- Three independent halt vectors: drawdown, daily loss and bankruptcy.
- Deterministic scripted BUY3/SELL3 plan: six one-unit partial fills over causally later candles; exact cash, quantity, fee-inclusive basis, fees, high-water mark and realized P&L after each fill with varying prices. The scripted plan is not a port/qualification of the full strategy registry.
- Replay/corruption, identical/conflicting idempotency, stale revisions, competing writers, repeated bars, kill/suspension and UTC day boundary protection.

Money comparisons use exact BigDecimal numeric equality, never epsilon/tolerance or Double. Python monetary strings are validated as decimal values; UTC representations normalize through Instant. No approximate equality is accepted for cash/basis/inventory conservation. A complete exit leaves zero inventory and zero basis.

Local JVM test gate passed during implementation. Actual ARM64 instrumentation creation and recovery passed across force-stop; final repetitions and x86_64 execution are recorded in CI/delivery evidence. The new job has no PostgreSQL, Redis, FastAPI or backend credentials. The existing server-backed device job is kept separately.

Exclusions: complete technical indicator catalogue, forecast/model calibration, real-data quality policy, arbitrary strategy lifecycle, multiple outstanding orders, varying provider/exchange behavior, comprehensive timestamp/rejection mapping for the entire Python engine, FX and derivatives. This is cross-language acceptance of the listed vectors and bounded native foundation, not equivalence of all177 Python modules. Physical-tablet/endurance/performance qualification remains absent.

## Final local observations

JVM: 11 tests passed, zero skipped/failures. ARM64 API35 final create: `OK (1 test)` in 0.181s; recover after force-stop: `OK (1 test)` in 0.210s. Native measured body: create173ms/PSS159,455KB; recover201ms/PSS168,334KB. Distinct process IDs in evidence confirm separate processes. These are single measurements including app/ART overhead, not peak-RAM or sustained-load qualification. Final cash997.51274875 EUR, fees0.66100125, realized P&L−2.48725125, inventory0 and basis0 exactly match the Python fixture. Synthetic loss is a mechanical test outcome, not empirical performance.

Raw logs are in evidence/arm64-*.txt. CI must separately qualify x86_64 and the final pushed SHA. Force-stop occurs between committed events; power-loss/mid-write endurance has not been tested.
