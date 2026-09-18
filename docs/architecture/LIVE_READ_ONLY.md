# Phase 26: private live read-only observations

## Boundary and assessment

The clean Phase 25 baseline was bf2240a49f3083f78318b4458b70c49f3d005149. Phase 26 adds
`broker_readonly` to the Python modular monolith. It observes Binance Spot accounts explicitly,
without a strategy dependency, a broker execution interface, public account endpoints or startup
polling. The public Coinbase historical adapter remains separate. Every future order still requires
the intelligence → forecast → directional → strategy → portfolio → risk → leverage assessment →
execution → broker boundary; nothing here authorizes such an order.

The initial gap was the absence of private-account connectivity and account-bound local expectations.
The design deliberately requires an independently verified `LocalState`, including local market/asset
bindings, instead of treating simulated PAPER balances or an observed broker response as a reconciled
local ledger. It never changes Phase 16 accounting entries, PAPER headers or broker state.

## Native provider and credentials

The native adapter uses only HTTPS GET against `https://api.binance.com`, with this fixed endpoint
allowlist: `/api/v3/time`, `/api/v3/exchangeInfo`, `/sapi/v1/account/apiRestrictions`,
`/api/v3/account`, `/api/v3/openOrders`, `/api/v3/myTrades`. No order creation, cancellation,
transfer, withdrawal, websocket subscription or generic HTTP mutation method exists.

Official contracts consulted on 2026-09-18:

- [Binance Spot REST API](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md).
- [Wallet account API and key permission inspection](https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account).

Private GETs use the documented HMAC-SHA256 signed query and API-key header. The reader rejects
clock skew above five seconds and uses a 5000 ms receive window. It checks the full documented
permission response before account access and again after capture: reading must be enabled and all
nine write/trading/transfer permission flags must explicitly be false. Absent, extra or non-boolean
privilege fields fail closed. This strict schema may reject a legitimate key when a venue omits a
field or changes its API; that needs contract review, never a missing-field=false fallback.
`enableFixReadOnly` can be true or false; IP restriction is recorded but not required by this code.
Operators should restrict the key to the necessary account and their network. Account-level
`canTrade`/`canWithdraw` are not interpreted as API-key privileges.

Credentials are environment-only Pydantic SecretStr fields, excluded from serialization and repr:
`PA_BINANCE_READONLY_API_KEY`, `PA_BINANCE_READONLY_API_SECRET`, and
`PA_BINANCE_READONLY_EXPECTED_UID`. No dotenv loader, frontend, database, logging or secure-store
implementation is added. There is no hardcoded credential. The expected numeric UID must match the
broker response; persisted identity is SHA256 of the venue namespace plus UID, not the raw UID or
API key. This pseudonym is not an authentication proof and may be guessable for small UID spaces.

The native transport disables ambient proxies and redirects, retains normal HTTPS certificate
validation, bounds reads to 2 MB and timeouts to ten seconds, and accepts HTTP 200 only. Requests are
spaced at least 0.5 seconds apart. There are no automatic retries: network, rate-limit and dependency
failures cannot yield readiness. CLI exceptions are sanitized, including Pydantic errors that might
otherwise echo environment inputs. No upstream message, response body, signed URL or key is logged.

## Observation and financial contracts

Models are frozen and forbid extra fields. Monetary quantities use bounded Decimal values;
positions sum free plus locked in a private 80-digit Decimal context. Binance numeric monetary
inputs must be decimal strings, never binary floats, negative values or non-finite numbers.
All timestamps are UTC. Started/completed timestamps use the actual clock around I/O; trades retain
venue occurrence time and cannot occur after completion. Historical records are not backdated as
available at their trade timestamp.

The account must be SPOT with exactly SPOT permissions. All returned balances, including zero
balances, are retained. The spot inventory quantity is free + locked: it is not a derivative position,
borrowed quantity, cost basis, converted value, profit or risk-approved allocation.

The caller declares 1–10 native symbols and their Pocket Alpha market/asset/base/quote identity.
Metadata must return every symbol once, matching base and quote, TRADING status and explicit spot
eligibility. Price tick, quantity step, quote precision and a hash of the full metadata are recorded.
Metadata is descriptive, not an execution sizing validator; unsupported future order filters cannot
be presumed executable.

Open orders are read across the account. Any order outside the configured symbol scope blocks the
capture. Duplicate orders, unknown statuses/types, invalid quantities, fully executed open orders,
status/quantity disagreement and zero-priced limit orders reject. NEW and PARTIALLY_FILLED are the
only statuses supported. Quote-sized MARKET orders with zero original base quantity are unsupported
and reject conservatively. The hash of each entire venue order retains detection of changes to
stop/OCO/trailing parameters without introducing cancellation or interpreting contingent execution.

Trade history requires an explicit inclusive `from_id` for every symbol. Each page must advance
strictly; duplicates, backward IDs and wrong symbols reject. IDs need not be contiguous. A short
page ends the bounded scan; a full final allowed page blocks instead of silently declaring completion.
Default bounds are 1000 trades/page, ten pages/symbol and thirty seconds for the entire observation;
configurable hard maxima are 1000/page, twenty pages and 300 seconds. Returned history means the
available API records for the declared symbols/cursors, not certified lifetime account history.

Trades retain price, base and reported quote quantity, BUY/SELL side, order/trade IDs, actual reported
commission and commission asset. Reported quote quantity must agree with price × base quantity
within one native quote-precision quantum, using private Decimal arithmetic. Commissions in BNB or
another asset are not converted, assumed zero or folded into fabricated P&L.

Balances and full-account open orders are read before and after metadata/history. Any difference,
identity change, altered permissions, future trade, exceeded deadline or invalid response aborts.
This catches observed changes; separate REST calls are not atomic and cannot detect every transient
change that returns to the same state. Trade and metadata endpoints do not receive atomic sequence
numbers. Partial captures never produce an accepted observation.

Native transport observations are labelled REAL; injected transports are forced SYNTHETIC. That
label is acquisition provenance, not a claim of profitable trading or independent provider attestation.

## Reconciliation and local use

`reconcile` compares origin, account identity, all instrument bindings/metadata, free and locked
balances, full orders, actual trades and history scope against a supplied independently verified
local state. Collections compare in canonical order; Decimal values compare numerically. Mismatches
produce explicit reason codes and BLOCKED status, without auto-import, synthetic fills or ledger
repair. Local revision and recorded-at timestamp are hashed; local evidence must predate capture.
Unknown local state, synthetic observation, future/stale capture or excessive observation span
cannot be ready. Age limit defaults to thirty seconds and is a caller policy, not a recommendation.

Even MATCHED retains `execution_authorized=false` and `live_trading_enabled=false`. It means current
read-only reconciliation under declared scope, not strategy promotion, risk approval or trading
readiness. Local verification is a caller attestation, not a cryptographic signature. Importing an
observation as expected state solely to force a match invalidates that attestation.

Create a private, ignored `.private/` directory with account-holder-only access. A request file has:

```json
{
  "instruments": [{
    "symbol": "BTCUSDT", "market_id": "binance:BTCUSDT", "asset_id": "BTC",
    "base_asset": "BTC", "quote_asset": "USDT"
  }],
  "history_scope": [{"symbol": "BTCUSDT", "from_id": 0}]
}
```

These example identities are configuration, not seeded market data or a trading recommendation.
Provision credentials privately in the three environment variables, then run explicitly:

```powershell
.venv/Scripts/python.exe -m pocket_alpha.broker_readonly.cli --request .private/request.json --output .private/observation-001.json
```

Without `--local-state .private/local-state.json`, the observation can be inspected but reconciliation
is BLOCKED with LOCAL_STATE_MISSING (exit 2). A LocalState file follows the typed AccountState schema,
with revision, recorded_at and independently_verified=true after independent local ledger review.
A matched current observation returns exit 0. Configuration, capture or reconciliation failure returns
exit 2. The CLI prints only sanitized status/error codes; it writes the complete typed observation
and reconciliation receipt to a new file using O_EXCL and never overwrites a receipt. Credential
material is never part of the file. Financial records and client IDs remain sensitive: do not commit
or share them. Mode 0600 applies where supported; Windows directory ACLs remain the operator's
responsibility. A receipt is append-only by tool convention, not tamper-proof storage or encryption.

## Migration, compatibility and limits

No schema, dependency, API or frontend migration is introduced; Alembic remains at 0015. Local files
are the explicit Phase 26 observation/reconciliation persistence, separate from portfolio/PAPER
ledgers. No authenticated account was available for a real integration probe in this task. Tests
use synthetic transports and mock the native opener; no real account, key, balance, fill or order
result is claimed.

New Python source changes the global PAPER source-tree identity. Existing journals stay readable and
replayable but new processing requires the matching current runtime/evidence. Do not rewrite old
headers, sealed research evidence or checkpoints to evade RUNTIME_IDENTITY_CHANGED.

Debt retained: authenticated venue qualification and geographic availability, a secure-store adapter,
private encrypted/audited persistence and access-controlled account UI, verified Phase 16 ledger
mapping/deposit/transfer handling, atomic streams, larger/history-retention proof, additional venues
and independently audited scope changes. No profitability, calibration, leverage, withdrawal or
execution claim is introduced. Phase 27 is next and has not been started.
