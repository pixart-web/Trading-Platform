# Intelligence architecture
Normalized, validated, non-stale provider data feeds a shared intelligence service. Validate time,
ordering, gaps, duplicates, sequences, outliers, connection state and order books; deterministic
replay must preserve availability time. Keep provider metadata and trading sessions explicit.
Indicators are versioned parameterized causal FEATURES, never an unvalidated voting system.
Trend, momentum, volatility, volume and price action feed structural and probabilistic regime models.
Confirmed swings record when confirmation became available; zones retain bounds, touches, recency,
strength, confidence and evidence. No future bar may retroactively change an earlier feature snapshot.
Multi-timeframe conclusions retain disagreements and flag trades against higher-timeframe trends.
Fundamental, derivatives, news and macro are optional, availability-timestamped contextual features.
Their relevance must be measured by asset, horizon and regime.
Pocket Score has configurable inspectable weights. Opportunity Score has a versioned economic
formula including calibrated probability, move, costs, liquidity, uncertainty and risk/reward.
No scoring, indicators or recommendations are implemented in phase 0.

Phase 1 now provides quality-checked historical ingestion and fail-closed replay. Future analytical
consumers must use the trusted replay boundary and explicit freshness/session policies described
in MARKET_DATA_ARCHITECTURE.md. Read-only inspection responses are not implicitly trusted input.

Phase 3 implements the initial five-family technical feature catalogue and shared service described
in TECHNICAL_INTELLIGENCE.md. Snapshots retain causal availability, prefix hashes, parameters,
versions and explicit unavailable states. No scoring, classifications, predictions or recommendations
are introduced; advanced catalogue extensions and empirical feature evaluation remain future work.

Phase 4 implements confirmed swings and versioned close-break structure in MARKET_STRUCTURE.md.
It distinguishes pivot position from confirmation and availability, retains evidence, and does not
convert structure into trade decisions or probabilities. Analytical hashes share one canonical encoder.

Phase 5 adds SupportResistance over trusted replay and confirmed structure pivots. Immutable zones
retain fixed bounds, contact episodes, rejections, role flips, recency and explained heuristic strength.
Confidence remains null/UNCALIBRATED. See SUPPORT_RESISTANCE.md for precise conventions and limits.

Phase 6 adds intelligence/multi_timeframe: independent native-resolution analyses at one causal
cutoff, unanimous structural context, explicit disagreement and higher-timeframe opposition.
It reuses the existing kernels after one trusted replay per frame, with explicit freshness and
unavailable states. No persistence, HTTP, UI or execution dependency is added. See MULTI_TIMEFRAME.md.
