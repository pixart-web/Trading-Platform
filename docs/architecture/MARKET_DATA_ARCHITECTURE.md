# Universal market data — Phase 1
## Scope and boundaries
Only domain, historical ingestion, storage, quality, read-only API and replay are implemented.
No public provider, credential, order route, indicator, forecast, signal or UI is added.
The optional real-provider integration is deliberately deferred. Fixture data is synthetic and
never seeded into application startup. An empty production database returns empty inspection
results, never invented observations.

## Identity and normalized schemas
AssetId identifies the economic asset independently of listings/providers. Asset contains symbol,
name and AssetType (all nine planned classes). Venue represents a listing context; Market links
one asset to a venue and quote currency, with its display symbol. BTC can have BTC/EUR and BTC/USD
markets just as a stock can have different listings. ProviderMapping alone contains external
instrument IDs, keyed by source + market, with unique source + external instrument ID.
AssetId, Symbol, Currency and market identifiers are constrained value aliases. Existing Asset
construction is compatible; formerly unbounded strings now have explicit length/format limits.

Candle, Trade, Quote, OrderBook and book levels are frozen Pydantic models. Monetary fields are
finite Decimal, positive prices, nonnegative volume and quote size; trades/book quantities are
positive. Supported precision: 38 digits total, at most 18 fractional and 20 integer digits.
Negative-priced future contracts are not supported by this initial price policy and must require
an explicit instrument policy before such data is accepted. Initial four asset classes share models.
Aware timestamps normalize to UTC; naive timestamps are rejected. Book levels require unique,
sorted prices, correct sides and uncrossed bids/asks; sequence is optional nonnegative metadata.
Session and market status models represent explicit context, not an exchange-calendar service.

## Candle windows and calendars
A candle is a completed nominal interval [open_time, close_time), with close_time exactly
open_time + timeframe.duration. Receipt cannot precede close. 1d and 1w currently mean fixed
24-hour and 7-day windows, not exchange-local or daylight-saving calendar periods. Provider
inclusive-close timestamps must be normalized by future adapters. Partial/current candles are
rejected; variable-duration session bars need a future explicit schema extension.
CandleQuery selects open times in [start, end), bounded to 10,000 regular slots. It uses either
a continuous grid anchored at start, or an explicitly supplied sorted unique expected_opens
schedule of at most 10,000 timestamps. Use the latter for closed sessions, holidays or other
noncontinuous markets. No calendar is inferred from asset class. An empty explicit schedule
means no bars are expected; an empty regular series means missing data.
TradingSession is a domain representation; converting authoritative calendars into the supplied
schedule is a caller/adapter responsibility.

## Providers and ingestion
Ports: MarketDataProvider, HistoricalMarketDataProvider, StreamingMarketDataProvider and
AssetMetadataProvider. Streaming is a contract only, without connection/reconnect implementation.
Historical adapters return bounded pages of normalized field mappings, still untrusted until
Candle validation and quality checks pass. Pagination has a 100-page/10,000-record ceiling,
detects cursor loops and propagates explicit ProviderError. FixtureProvider preserves order,
duplicates and errors, copies payloads and supports deterministic test pages.
No retry/rate-limit logic is claimed because no network adapter exists. A future network adapter
must add timeouts, bounded retries, rate-limit handling and explicit failure without fallback data.

HistoricalIngestion requires asset identity, market query, freshness policy, Clock and a registered
provider mapping. It validates the entire bounded import before writing anything. Invalid OHLC,
prices, volume, malformed fields, future timestamps, stale data, duplicates, out-of-order records,
wrong market/source/timeframe, unexpected slots or gaps reject the complete import.
Callers own the SQLAlchemy transaction: commit after success and roll back on error. Metadata
registration reuses identical assets/venues/listings/mappings and rejects conflicting metadata.
Concurrent metadata registration may raise a uniqueness error; callers may retry the full
transaction. Candle concurrency uses database ON CONFLICT and compares the stored value.

## Persistence
PostgreSQL remains authoritative. Tables: assets, venues, markets, provider_mappings, candles.
Candle primary key (market_id, timeframe, open_time) is also the historical range-query index.
Foreign keys protect asset/venue/mapping relationships, including candle source + market mapping.
Database checks protect OHLC, nonnegative values and timestamps. Domain precision validation
prevents silent rounding during supported application writes. Identical repeated candles are
skipped; changed OHLC/volume/source/close-time conflicts roll back the whole write batch.
First received_at is preserved on identical re-import. No correction overwrites history silently.
Decimal is NUMERIC(38,18) in PostgreSQL. SQLite unit tests use text for exact decimal roundtrips;
numeric CHECK constraints are PostgreSQL-only and explicitly exercised by integration tests.
Do not use SQLite as production persistence. Trades/quotes/books and sessions are domain-only
in this phase; no trade tape or streaming store is claimed.

## Quality and consumer boundary
DataQualityResult includes validity, severity, stable reason codes, affected input indices,
missing timestamps, source, evaluation time and warnings. Missing data is never filled.
FreshnessPolicy.max_age=None explicitly means historical age is allowed, not that data is live.
A finite threshold evaluates each candle by close time; recent receipt cannot rejuvenate old prices.
Future tolerance is separately configurable and defaults to zero.
Intelligence must use HistoricalIngestion or MarketReplay.replay, not raw storage inspection.
MarketReplay.inspect and read-only API deliberately expose diagnostic data alongside quality.
A false quality.valid flag MUST NOT be treated as trusted input.

## Replay
MarketReplay reads bounded canonical stored data, revalidates it with the caller's policy/Clock,
then sorts by (received_at, open_time). ReplayEvent.available_at is the preserved receipt time,
never the opening timestamp. Ties have deterministic order. Repeated reads of an unchanged
dataset and FrozenClock yield identical events/results. Delayed observations cannot appear early.
replay() fails closed for gaps/staleness/errors. inspect() retains real events and gaps for diagnosis;
trusted_events() raises DataRejected unless valid. Empty expected-closed schedules replay empty.
Historical imports received today therefore replay no earlier than today: research must not
invent historical availability. Vendor availability provenance requires a future adapter policy.
Replay is bounded in memory, not yet a million-row streaming snapshot; corrections are rejected,
but concurrent additions between separate replay calls can change the dataset.

## API
GET /api/v1/assets, GET /api/v1/assets/{asset_id}, GET /api/v1/markets and
GET /api/v1/markets/{market_id}/candles. Lists have limit 1..1000 and offset 0..100000.
Candles require timeframe, timezone-aware start/end and limit 1..1000. Unknown identities: 404;
bad/oversized ranges: 422; unavailable database: 503 without connection details.
Candle response includes candles, quality, truncated and next_start. Page truncation is explicit,
and quality assesses completeness relative to the requested range, so truncated pages are not
claimed complete. API uses historical age policy and continuous expected intervals: it is an
inspection API, not a session-aware analytical feed. Use application query schedules for sessions.
There are no write endpoints. Initialization/import is an application-service operation.

## Observability and clock
Phase 0 had no injectable Clock despite the Phase 1 premise; common.clock adds Clock,
SystemClock and FrozenClock. Deterministic quality/ingestion/replay use the supplied Clock.
Structured logs identify ingestion start/completion, stable rejection reasons (gaps/stale/duplicates),
provider and persistence failures, without raw payloads or credentials. Metrics is an injectable
counter port (NoopMetrics by default); no metrics backend is falsely advertised.
Readiness now checks that the candles table exists as well as Phase 0 dependencies.
