# Real public market data — Phase 20

## Adapter and identity

CoinbaseHistoricalProvider implements the existing historical provider port with unauthenticated GET
of Coinbase Exchange spot candles. It requires an explicit source/market/product mapping and accepts
native 1m/5m/15m/1h/1d buckets. Other timeframes are rejected without resampling or invented bars.
Boundaries must align to native UTC buckets. Each page requests at most 299 intervals to respect the
vendor's 300-candle limit even with inclusive boundaries. Pagination is by time window; vendor bars
outside that page window are filtered to avoid overlap, then bars are ordered. Missing no-trade
intervals remain gaps, not zero-volume invented bars, and strict ingestion rejects an incomplete grid.

Vendor arrays are time/low/high/open/close/volume. JSON floating values parse directly to Decimal;
prices/volume are never routed through binary float arithmetic. Epoch timestamps become aware UTC;
receipt is captured after each HTTP response. Existing whole-batch quality checks reject gaps,
duplicates, invalid OHLC, wrong source/market, future or partial candles before canonical persistence.
No fixture fallback exists. Explicit reimports preserve the first canonical receipt; conflicting OHLC
requires a separate correction policy rather than overwriting history.

The frozen dataset also retains the Market, Asset and Venue with quote currency, and verifies the
Coinbase venue, native product, base symbol and quote currency before accepting origin REAL.
Synthetic sources use origin SYNTHETIC. A single dataset cannot mix candle sources. REAL is provenance
of an explicit operator import, not a cryptographic attestation by the vendor.

## Public transport limits

PublicClient accepts HTTPS GET only, with 10-second default timeout, 2 MB response limit, three default
attempts and 0.5-second minimum local request spacing. Operator-configurable limits are bounded.
It retries transport failure, 429 and 500/502/503/504 with bounded exponential delay; Retry-After seconds
or HTTP-date are respected when within a five-second wait budget. A longer/negative/nonfinite embargo
fails instead of shortening the vendor's wait. Other statuses fail immediately. Redirected responses
must preserve HTTPS origin; TLS verification is not disabled. Error responses close their streams.
Bodies, credentials and connection details are not logged. Limits are per client instance; multiple
processes may still encounter vendor rate limits. No real orders or credential requests occur.

Vendor references:
- [Coinbase Exchange candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)
- [Coinbase Exchange REST rate limits](https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits)

## Frozen research datasets

market-dataset-1.0.0 freezes REAL/SYNTHETIC origin, source/product mapping, economic identities,
query/timeframe, capture time and exact candles. SHA-256 validates the canonical serialized inputs.
DatasetRepository stores immutable JSON under a UUID; reads verify integrity and quality. It provides
no update/delete operation. An altered payload with an unchanged digest is rejected. Hashes detect
accidental changes; someone with database write access can recompute a hash, so this is not a signature.

Stored replay sorts deterministically and releases every candle no earlier than dataset capture. This
conservative policy never retroactively invents local historical availability. Native candle receipt
is also retained. Downloading January 2025 prices today does not prove an as-traded January 2025 feed
or a profitable causal strategy. No survivorship protection, streaming capture or economic backtest is
claimed. Existing MarketReplay still replays canonical receipt times; frozen datasets are the stable
research boundary and avoid concurrent additions changing inputs.

## Explicit import and evidence commands

Production application import requires previously registered Asset/Venue/Market/ProviderMapping and
migrated PostgreSQL. Nothing imports at application startup:

    python -m pocket_alpha.market_data.import_public --asset-id crypto:BTC --market-id coinbase:BTC-USD --timeframe 1h --start 2025-01-01T00:00:00+00:00 --end 2025-01-02T00:00:00+00:00

The command uses secure Settings database configuration and commits the import plus frozen dataset
atomically. It prints dataset identity/hash only. Public Coinbase requests require no credentials.
For explicit isolated local evidence, with public network access:

    python -m pocket_alpha.market_data.smoke_public --public-read

This command registers BTC/USD and a global Fed-news entity in a unique local SQLite database,
imports actual public candles/news, reloads after commit and compares replay/snapshot hashes. It writes
REAL-labelled evidence and dataset JSON to git-ignored data/local. This is an intentional isolated
smoke, not a production database fallback. Tests/CI never call it and never depend on public network.
All automated HTTP fixtures are explicitly synthetic. Evidence details are in the Phase 20 report.

## Migration and open work

0011 adds context_entities, context_mappings, context_observations and market_data_datasets only.
Downgrade removes these histories/datasets; export/backup before rollback. Existing accounting,
forecasts, facts and candles are untouched. PostgreSQL execution/row locking, Redis readiness and
Docker image validation remain separate deployment checks. Native derivatives, stock/index/macro
numeric feeds, streaming capture, corporate actions and provider correction workflows are outstanding.
No profitability, live readiness, broker permission or execution activation follows from this gate.
