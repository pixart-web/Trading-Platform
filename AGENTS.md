# Pocket Alpha engineering constitution
Read docs/product/PRODUCT_VISION.md, architecture documents, risk and validation policies,
and docs/roadmap/ROADMAP.md before implementation. Inspect existing changes and preserve them.
Implement only the earliest incomplete phase authorized by the user; report assessment,
gaps, debt, design, migration risks, changed files and acceptance criteria before production edits.
The mission is sustainable net compounded capital growth under explicit drawdown and ruin limits.
Never fabricate data, probability, confidence, profitability, fills or test results.
Use a Python modular monolith and one shared intelligence layer for all experiences.
Mandatory boundary: market data → intelligence → forecasts → directional analysis → strategy
→ portfolio → risk → leverage assessment → execution → broker.
Strategies cannot access brokers. Every order requires risk approval.
Timeframe and forecast horizon are separate. Monetary arithmetic uses Decimal; timestamps use UTC.
Forecasts are immutable; outcomes are separate records. Scores are not probabilities.
Version features, scores, models and research datasets. Prevent look-ahead and final-test optimization.
Live execution stays disabled by default; this foundation cannot enable it. No tests or CI real orders.
Never commit or log secrets or grant withdrawals. Treat dependency failures as not ready.
Run ruff check, ruff format --check, mypy and pytest for each task; run migration/integration/frontend
checks when relevant. Report exact results and unexecuted checks. Never weaken valid tests.
Completion report: summary, phase, architecture, complete file list, migrations, tests/commands/results,
financial coverage, limitations, security, economic assumptions, debt and next phase. Do not start it.
