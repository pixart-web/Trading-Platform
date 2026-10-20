# Live spot qualification

`LIVE_SPOT_ENGINEERING_READY = NO` for native real-money submission. The venue-neutral engine, Decimal arithmetic, risk checks, journals, UNKNOWN handling and synthetic contract tests are substantial engineering evidence, but authenticated venue conformance, write adapter qualification and operational drills are absent.

Activation requires: selected venue/account; trading-only credentials with withdrawals disabled; permission and account identity verification; instrument/minimum metadata; sandbox market/limit/partial-fill/cancel/reject tests; timeout/duplicate/reconnect/restart tests; fee and balance reconciliation; independently approved allowlists and limits; monitoring; incident/kill-switch drill; paper-to-live parity review; security sign-off; and deliberate operator authorization naming account, venue, instruments and limits.

`LIVE_SPOT_ENABLED = false`

`LIVE_SPOT_ACTIVATION_AUTHORIZED = NO`
