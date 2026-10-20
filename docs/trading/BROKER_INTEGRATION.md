# Broker integration

The repository implements venue-neutral spot and derivative request, risk, journal, reconciliation and qualification models. Binance support is limited to authenticated query/read-only behavior and native spot qualification scaffolding; derivative native dispatch does not exist. No arbitrary venue was selected and no credential was created.

Required venue adapter behavior: inspect account identity and permissions; load instrument tick/lot/minimum metadata; use deterministic client order IDs and idempotent submission; persist PREPARED before I/O; treat timeouts as UNKNOWN; reconcile before retry; record acknowledgements, rejections, partial fills, cancellations and fees; recover on restart; update portfolios only from confirmed fills. Withdrawals/transfers are outside the capability boundary.

External prerequisites: owner-selected venue/account, IP restrictions, trading-only keys, approved instruments, sandbox/testnet where available, official permission/metadata schemas, rate limits, WebSocket and REST recovery contract, fee tiers and an independent credentials ceremony.
