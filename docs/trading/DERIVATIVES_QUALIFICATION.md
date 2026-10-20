# Derivatives qualification

`LIVE_DERIVATIVES_READY = NO`. Derivative qualification remains independent from spot. Synthetic models cover Decimal collateral, reservations, funding/fees, reduce-only closure, UNKNOWN reconciliation and finite liquidation stress. The engine explicitly rejects native dispatch as unqualified.

A venue-specific implementation must still verify contract multipliers, inverse/linear settlement, mark/index rules, maintenance tiers, cross/isolated margin, funding schedule, collateral haircuts, reduce-only behavior, position mode, liquidation/ADL events and authoritative reconciliation. Generic calculations cannot claim venue liquidation accuracy.

`LIVE_DERIVATIVES_ENABLED = false`; spot approval cannot change it.
