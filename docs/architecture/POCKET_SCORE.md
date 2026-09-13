# Pocket Score architecture

Phase 10 introduces a configurable, explained setup-quality score after intelligence and forecasts.
It does not produce a direction, rank a trade, estimate success probability or represent expected
return. Directional LONG/SHORT/NO_TRADE analysis belongs to Phase 11 and economic opportunity
ranking belongs to Phase 12.

## Input and configuration contract

A Pocket Score specification declares a version, one to sixteen uniquely identified components,
a positive weight for each component, whether each is required and a minimum available-weight
coverage. The engine does not prescribe component names or convert existing indicators into
normalized values. Each producer must supply an independently defined, versioned normalization in
the closed range 0 to 100 and causal evidence. This prevents an arbitrary indicator transformation
from being presented as a validated product score.

Inputs must match the configured component order exactly. An available component contains its
normalized value, normalization version, availability time and one or more canonical evidence
snapshots. Evidence cannot postdate component availability, and component availability cannot
postdate the score as-of time. An unavailable component contains an explicit reason and no plausible
value or evidence.

## Calculation and explanation

For available components, the engine computes:

    coverage = available configured weight / total configured weight
    effective weight = configured weight / available configured weight
    contribution = normalized value * configured weight / available configured weight
    Pocket Score = sum of contributions

All arithmetic uses Decimal in an isolated 50-digit context and publishes values to 30 decimal
places. A deterministic rounding residual is assigned to the available component with the highest
configured weight, with configuration order breaking ties. Effective weights sum exactly to one and
the published score exactly equals the sum of published contributions.

Every result retains market, asset, candle timeframe, as-of and generation timestamps, score
version, configuration hash, input hash, coverage, total/available weights and a component-by-
component explanation. Each explanation includes label, required flag, configured/effective weight,
raw normalized value, contribution, normalization version, availability and source evidence.

## Missing inputs and failure behavior

A missing required component returns an unavailable score with
REQUIRED_COMPONENT_UNAVAILABLE. Optional components may be omitted only when the remaining
configured weight satisfies the declared minimum coverage; their absence and reason remain visible
and the available weights are renormalized. Coverage below the threshold returns
INSUFFICIENT_COMPONENT_COVERAGE. A configuration with no available components returns
NO_COMPONENTS_AVAILABLE even when its minimum coverage is zero.

An unavailable result publishes no score or partial contributions. Values and evidence from inputs
that were actually available remain visible for diagnosis, while their effective weight and
contribution remain null.

## Boundaries and limitations

The module is an in-memory deterministic domain service. It adds no database migration, API, UI,
external provider, model artifact or dependency. It cannot reach strategies, portfolios, risk,
leverage, execution or brokers, and it cannot bypass any future risk decision.

Tests use synthetic normalized inputs. The repository ships no empirically validated component
normalization, default financial weights, thresholds, real dataset or claim that a higher score
predicts returns. Calibration, temporal outcome studies, sensitivity analysis and score governance
remain required before a configuration can have financial meaning. Phase 11 is not started.
