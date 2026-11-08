# Autopilot runtime — blocked

PAPER_AUTOPILOT_READY=NO. The application does not run an automated trading loop. It explicitly blocks automatic orders because the production SMA trend family requires forecast and directional evidence that has not been ported/qualified. No arbitrary SMA crossover has been relabelled as an approved production strategy to bypass this boundary.

Manual execution is active-session only. Leaving the Activity, losing connection, changing markets or an extended observation gap clears process-local order eligibility. Restart reconciles committed events but does not resume execution. Newly processed fills require an actual fresh eligible bar and explicit user action. No delayed orders or missed fills are fabricated.

WorkManager is not used as a continuous financial clock. There is no claim of 24/7 Doze/process-death survival. Start/pause/resume strategy orchestration, durable suspension/uptime reporting and complete restart/reconnect controls remain work. Before enabling them, qualify the complete forecast/directional/strategy path against the Python oracle, add lifecycle/interval journals, and test actual Redmi battery/thermal behavior. See the prior runtime architecture and device compatibility notes.

After Preview 0.1, [native strategy research review](NATIVE_STRATEGY_REVIEW.md) adds oracle-tested decision projections and UTC horizon conventions. The operational adapter has no forecasts and emits a read-only explained NO_TRADE. This is not a strategy runtime, lifecycle promotion, complete directional engine or authorization to automate PAPER orders. PAPER_AUTOPILOT_READY remains NO.
