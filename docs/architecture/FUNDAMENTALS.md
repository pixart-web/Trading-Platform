# Fundamentals boundary — Phase 18

Corporate numerical facts are independent of candle resolution, forecasts and trade authorization.
Explicit asset/provider mappings prevent ticker guessing. The SEC mapping accepts registered stocks
only. Unmapped instruments return NO_POINT_IN_TIME_FUNDAMENTALS, including crypto. No startup import,
synthetic fallback, broker dependency or execution path is introduced.

Facts are immutable typed Decimal values, persisted as versioned JSON decimal strings. Each preserves
source concept, source record, accession, currency (including USD/shares), reporting period, fiscal
labels, publication date, availability/ingestion instants and revision linkage. Distinct XBRL concepts
are retained even when they map to the same analytical metric; they must not silently be added.

SEC CompanyFacts exposes filing dates rather than exact acceptance times in its observations.
The stored publication timestamp is a UTC date representation, not a verified intraday release.
Availability is conservatively the actual ingestion time. Imported filings cannot populate a
historical cutoff before ingestion. A later accession adds a new immutable fact; historical snapshots
select only facts available AND ingested by their cutoff. Original facts remain accessible.
A late older filing cannot supersede a newer publication. Same-day revision ordering uses source
record order and must not be treated as verified intraday publication order.

The real read-only SEC adapter requires an operator User-Agent/contact and explicit numeric CIK.
It requests one document (no pagination), bounds bytes to 20 MB and records to 10,000, spaces requests
by at least 0.2 seconds per adapter instance, bounds timeout/retries and rejects long retry embargoes
rather than retrying early. Production-wide distributed throttling is not implemented; ingestion is
operator-invoked, not a scheduler. Transport is injectable for synthetic test fixtures.
Malformed numeric facts, wrong CIK, network errors and exhausted retries fail explicitly.
No tests contact SEC. The adapter does not establish real price-data readiness required by Phase 20.

The application service gathers bounded provider pages, rejects cursor cycles/conflicting records,
validates the entire batch before writes and leaves commit/rollback to the transaction owner.
An asset-row lock serializes PostgreSQL imports; database uniqueness protects source identities.
Application callers must roll back failures. Public API is GET-only:
GET /api/v1/assets/{asset_id}/fundamentals?as_of=<aware ISO timestamp>, with no-store responses.
Future cutoffs and unknown assets fail; bounded history overflow fails rather than truncates silently.

Migration 0009 adds mappings and fact tables/index. Upgrade is additive. Downgrade destroys fundamental
history and requires an export/backup. It does not change portfolios or existing forecasts.
The current adapter covers revenue, diluted EPS, gross/operating/net income, operating cash flow,
capital expenditure, equity, reported cash and reported long-term debt concepts.
Financial context 1.0.0 computes annual revenue/EPS growth, gross/operating/net margins and free
cash flow from unambiguous compatible periods, currencies and units. Ratios use 80-digit intermediate
precision and round half-even to 18 decimal places. Annual observations require explicit FY labels,
annual filing form and a 350–380-day duration (engineering comparability bounds, not a calibrated
economic policy). Nonpositive growth bases are unavailable; losses and negative FCF remain negative.
Input UUIDs and a deterministic hash identify every computed feature; generated time is excluded.

Optional price_market_id and price_timeframe (default 1d) on
GET /api/v1/assets/{asset_id}/fundamental-context select a stored causal candle from an explicitly
identified market belonging to the asset. P/E requires positive annual diluted EPS, matching currency,
USD/shares-style units and a quote after the EPS became available. The complete quote provenance is
part of the context/hash. Quotes expose actual timestamps; no freshness guarantee or investment
recommendation is asserted. P/S, EV/EBITDA, ROE and ROIC remain explicitly unavailable without their
necessary comparable inputs. No quarterly annualization, comprehensive-debt claim, invented guidance
or earnings calendars is supplied. Provider-dependent coverage is a limitation, not fabricated data.

Operator import: set PA_SEC_USER_AGENT to the operator's legitimate identifying contact, then run
python -m pocket_alpha.fundamentals --asset-id <registered-stock-id> --cik <numeric-CIK>.
The command uses existing database settings, an explicit transaction and the real read-only adapter.
Repeated imports preserve original ingestion timestamps and reject changed immutable source content.
There is no public import/write endpoint, credentials or provider scheduler.

Primary provider contract: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
Fair access: https://www.sec.gov/about/developer-resources
