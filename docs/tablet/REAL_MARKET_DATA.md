# Android-native public market data

PublicMarkets uses HTTPS GET only against api.exchange.coinbase.com, without credentials or broker endpoints. Product discovery admits online EUR spot IDs with validated base_increment and min_market_funds. The initial UI exposes BTC-EUR and ETH-EUR. Quantity-step metadata and minimum quote funds are distinct; the model's minimum quantity is one quantum, not a claim of an undocumented venue minimum.

Historical H1 OHLCV is requested for an explicit240-hour window. Numeric JSON lexemes remain decimal strings. Normalization validates schema, identity, positive OHLC, OHLC bounds, nonnegative volume, aligned UTC buckets, duplicates and closed bars. The requested window must be contiguous; missing native intervals block analysis. Provider receipt timestamps and source labels are stored locally. Cached observations remain visibly historical/disconnected until a new response succeeds.

[Official candle contract](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles) documents incomplete intervals and advises against frequent historical polling. Actual verification observed350 buckets despite the documented300 maximum. The client therefore bounds response bytes at2MiB and raw normalization at1024 rows, then filters to the explicit240-hour interval. It does not accept unbounded data or silently interpolate gaps.

Requests serialize at one per second; 429/5xx receive up to two bounded exponential retries. Historical refresh is limited to once per minute. Transport errors are reported; disconnected state blocks new orders. Redirects and automatic connection retries are disabled. A late response for a different selected market cannot overwrite the current market display. No WebSocket/live bid-ask/ticker is claimed: displayed prices are closed-bar proxies.

Actual ARM64 evidence: BTC-EUR,240 real candles, source coinbase-exchange-public, qualified local SMA READY, successful independently encrypted account restore. See INTEGRATION_TEST_EVIDENCE.md. Region/provider outages remain external dependencies; private API keys are never bundled into the APK.
