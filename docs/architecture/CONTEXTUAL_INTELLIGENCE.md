# Contextual intelligence — Phase 20

## Scope and boundary

One Python kernel exposes causal news, sentiment and macro observations to research. The normalized
port can represent asset/company announcements, earnings, regulatory events, market/news/social
sentiment and macro releases/indices/rates/commodities. This is schema coverage, not a claim that every
category has a configured feed. Native news coverage is the Federal Reserve's official RSS title,
HTTPS link and publication metadata. No full article, social scraping, guessed sentiment, probability,
profit forecast or execution permission is produced. Numeric sentiment and macro require explicit
normalized providers; none are enabled at startup. Missing categories remain unavailable.

Entities are immutable operator-registered ASSET/MACRO/TOPIC identities. ASSET requires an existing
asset link; other entities are global topics/series. Source/entity/external mapping is explicit and
immutable. Registration is atomic. Entity names describe registered identity; they are not historical
company membership or a point-in-time security master.

## Causal observations and revisions

Frozen context-observation-1.0.0 retains source, external entity/record identity, event key, revision,
event/publication/availability/ingestion timestamps, entity/asset link and source URL where supplied.
All timestamps are UTC. Numeric values use finite Decimal with 38/18 precision and explicit units.
Monetary macro currency must match its unit. Reporting periods cannot end after the observed release.
Sentiment is a bounded [-1,1] normalized score with an explicit method version, never a probability.
A declared method version does not prove calibration or economic validity.

The bounded port imports at most 100 pages/1,000 samples and rejects cursor cycles, future publication,
wrong entity and malformed values before writes. Availability/ingestion are captured after provider
I/O. Historical RSS publication dates do not imply earlier local availability. Stable source-record
UUIDs make reimport idempotent and preserve original times; a changed record requires an explicit
revision with a new source-record identity. Revisions link the same source/entity/event with consecutive
numbers, stable event time/units/currency/reporting period and ordered publication/availability/ingestion.
An entity row lock serializes writers on PostgreSQL; a savepoint rolls back the whole failed batch.
The transaction owner commits. Database uniqueness, mapping/self foreign keys, time ordering and
revision/supersession checks reinforce the models.

Snapshots reject naive/future cutoffs and filter all three knowledge timestamps by cutoff. They select
the latest available revision of each source/event, preserving other events. Known future calendar
news must be explicitly SCHEDULED and cannot masquerade as an observed macro release. RSS event_at
means the feed publication event; actual decision/economic-event time is not extracted or invented.
Coverage reports record presence, not freshness or trading readiness. Consumers must set an economic
recency policy. Snapshots expose no derived sentiment or macro regime when the input is missing.

context-snapshot-1.0.0 hashes feature version, cutoff, entity and ordered immutable observations,
excluding generation time. Models verify the hash. Stored history is bounded at 10,000 rows and
snapshot output at 1,000 events; exceeding bounds fails rather than truncating silently.

## Read-only API and public source

GET /api/v1/context/{entity_id}?as_of=<aware timestamp> returns context and unavailable kinds.
Unknown identity is 404; invalid cutoff is 422; storage failure is generic 503. Successful responses
are no-store. There are no HTTP write/import or order endpoints and no broker dependency.

FederalReserveNewsProvider requests only
https://www.federalreserve.gov/feeds/press_all.xml. It rejects malformed/oversized documents,
DTD/entities, missing metadata, non-HTTPS links and links outside the Federal Reserve origin.
The public HTTP client enforces bounded response bytes, retries/backoff and request spacing;
see REAL_MARKET_DATA.md. Network failures do not switch to fixtures. Publisher edits with unchanged
record identity fail explicitly; an automatic publisher revision-detection policy is future work.

Official source catalogue: [Federal Reserve RSS feeds](https://www.federalreserve.gov/feeds/feeds.htm).

## Limitations and security

No native numeric macro or sentiment feed/model, event relevance classifier, text NLP, automatic
Analyze/forecast recomputation, news trading or frontend view is introduced. Research consumes this
shared read model explicitly. No probability/confidence/profitability or real execution is claimed.
No credentials are needed or logged. Live configuration remains Literal[False]. PostgreSQL concurrency
and dependency readiness require separate service integration evidence; SQLite tests do not prove it.
