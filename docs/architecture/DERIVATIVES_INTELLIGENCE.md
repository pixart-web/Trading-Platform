# Derivatives intelligence — Phase 19

## Scope and identity

One Python derivatives module provides descriptive context to all future experiences.
It registers perpetual, dated future and vanilla option contracts separately from economic assets
and spot listings. The derivative: namespace, underlying asset/venue foreign keys and unique
source/external-contract identity prevent a spot identifier from becoming a derivative contract.
Registration requires an existing asset and venue. No startup data is seeded.

Immutable contract schema 1.0.0 preserves kind, underlying, venue, authoritative source identity,
quote/settlement currencies, contract multiplier and its units, cash/physical settlement,
reference index identity/currency, margin scheme and UTC publication/availability/ingestion.
Futures/options require expiry. Options additionally require strike, CALL/PUT and EUROPEAN/AMERICAN.
Perpetuals cannot have expiry or option fields. Contract economics cannot be silently rewritten.
Changes to actual contract specifications require a future explicit metadata-version migration;
dynamic reported margin characteristics are timestamped observations, not metadata edits.

## Observations and causality

The provider port returns bounded pages of normalized DerivativeSample values. It must assert one
coherent observed_at for all components in a sample, precise external identity and published_at.
No native network adapter or live feed is installed in this phase. Provider implementations must
validate vendor licenses, units, field timing and normalization before production use.
The application gathers up to 100 pages/10,000 observations, rejects cursor cycles, mismatched IDs,
conflicting source records/revisions and invalid contract fields before persistence. It captures
actual availability/ingestion AFTER provider I/O. Historical backfill is not retroactively available.

Immutable observations contain Decimal JSON strings, event/publication/availability/ingestion
times, deterministic UUID, source record and explicit revision. Revision N must supersede N-1 for
the same contract/event, with coherent publication/availability/ingestion ordering. Reimports retain
the original ingestion time. Row locking serializes PostgreSQL imports in the owner's transaction.
The caller commits/rolls back; no write/import HTTP endpoint exists.

Queries require available AND ingested AND published by an aware UTC-normalized cutoff. Latest means
latest market event, then its available revision. A correction to an older event cannot replace a
newer event. Unknown/not-yet-known contracts are unavailable. Future cutoffs fail. Limits fail
explicitly rather than claim complete truncated histories. No forecast horizon or candle timeframe
is inferred: derivative samples are events, not candles.

## Financial conventions

Funding is a signed fraction per explicitly supplied interval (seconds), tagged REALIZED or
INDICATIVE. No annualized yield, net return, realized cash flow or funding direction profit is inferred.
Open interest is explicitly normalized contracts, never assumed raw provider units.
Reported initial/maintenance rates require a denominator basis and rules reference. Supported rates
are fractions in [0,1], with maintenance <= initial when both exist. This limited representation
does not implement margin tiers, account risk, maximum leverage or liquidation.

Implied volatility is nonnegative ANNUALIZED_FRACTION; values above one are allowed and are not
probabilities. Adapters must convert percentage quotes explicitly. Greeks preserve provider-reported
value, name, unit, convention and model version; this module never estimates Greeks or fits options.
A reference/model label is provenance, not independent verification of the vendor's model.

Context feature version 1.0.0 calculates:
- derivative_minus_index = mark - index, in quote currency;
- derivative_minus_index_fraction = (mark - index) / index;
- simple_annualized_basis_act365f = fraction * 365 days / time from quote to dated expiry;
- open_interest_quote_notional = contracts * base-units multiplier * index, or contracts *
  quote-currency multiplier for inverse-style contract units.

These formulae require compatible units/currencies. Index currency mismatches suppress basis and
base-unit notional; no FX conversion is fabricated. Options do not receive future basis/OI exposure
formulae. Futures permit signed/zero marks, including negative prices. Perpetual marks must be positive;
option premiums may be zero but cannot be negative. Index prices are positive for supported basis.
Calculations use 80-digit intermediates and half-even rounding to 18 decimal places. Notional is
descriptive aggregate open interest, not position risk or approved exposure. Unsupported/extreme
values fail validation instead of truncating/clamping.

The basis sign is explicitly derivative-minus-index; it must not be confused with CME's commonly
used cash-minus-futures commodity convention. ACT/365F simple annualization is descriptive carry
scaling, not a forecast, compounded yield, arbitrage return or net profitability assertion.
Sources informing normalization/convention choices:
[CME glossary](https://www.cmegroup.com/education/glossary),
[Deribit ticker contract](https://docs.deribit.com/api-reference/market-data/public-ticker).
Deribit documents different raw open-interest units/delta conventions; no implicit adapter is claimed.

## Freshness, term structure and skew

Policy 1.0.0 maximum_age_seconds defaults to 300, configurable 1–86,400. This is an engineering
freshness bound, not a calibrated financial risk limit. Age uses event time. Missing, stale and expired
observations suppress all calculated metrics, retaining raw records for inspection with explicit status.
Generated time is excluded from hashes; inputs, versions, policy, cutoff and provenance are included.
No comparable data means a reason, never zero or a plausible estimate.

Term structure preserves all known unexpired future contexts in expiry/ID order. A COMPLETE mark-price
curve requires at least two compatible contracts and fresh nonmissing marks at the identical event time.
Comparison includes underlying, venue, source, quote/settlement currencies, reference index/currency,
settlement and multiplier/units. Missing quotes give PARTIAL; incompatible or unaligned contracts give
UNAVAILABLE. No interpolation, slope classification, cheapest-to-deliver adjustment, roll selection,
carry optimization or options volatility surface is implemented.

Explicit option pairing computes put_minus_call_iv_25delta only when CALL and PUT have compatible
metadata, same expiry/exercise style and simultaneous fresh IVs. Reported deltas must be exactly
+0.25/-0.25, price-ratio units, spot-unadjusted convention and matching provider model version.
No tolerance, nearest-strike/delta guess or conversion of premium-adjusted/inverse deltas is used.
Strikes may differ, as appropriate for matched deltas. Missing/incompatible evidence is unavailable;
no Black–Scholes, volatility fitting or statistical confidence is manufactured.

## API, migration and safety

GET /api/v1/derivatives/contracts?underlying_asset_id=&venue_id=&as_of=
GET /api/v1/derivatives/{contract_id}/context?as_of=&maximum_age_seconds=
GET /api/v1/derivatives/term-structure?underlying_asset_id=&venue_id=&as_of=&maximum_age_seconds=
GET /api/v1/derivatives/option-skew?call_contract_id=&put_contract_id=&as_of=&maximum_age_seconds=

All responses are no-store. Invalid inputs: 422; missing identity: 404; storage errors: generic 503
without connection details. No public write, order, strategy, broker, risk approval or leverage path.
All intelligence remains context. Live/derivative execution and Autopilot remain disabled.

Migration 0010 follows 0009, adding derivative_contracts and derivative_observations with identities,
source/revision uniqueness, foreign keys and cutoff indexes. Decimal values remain exact JSON strings.
Upgrade is additive. Downgrade deletes this history and needs backup/export. Existing candles, portfolios,
fundamentals and forecasts are untouched. PostgreSQL locking/constraints require real service integration.

## Limitations and future debt

No real derivative feed, production authentication, instrument discovery, contract-spec revision ledger,
exchange calendars, funding payments, order books, account margin tiers, liquidation calculations,
portfolio Greeks, options pricing/surfaces, settlement verification or frontend panel is supplied.
Provider claims require independent validation. Distributed ingestion throttling and market-data
adapter availability policy remain future work. This phase does not satisfy the Phase 20 real
market-price provider gate, authorize SHORT/leverage or approve deployment.
