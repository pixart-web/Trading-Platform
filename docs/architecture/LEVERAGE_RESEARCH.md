# Phase 25 — independent leverage research

## Scope and boundary

LeverageResearch.assess(LeverageRequest) is an offline pure calculation boundary after a caller's
portfolio/prior research-risk context. It does not import strategies, simulation, PAPER, execution
or brokers; existing spot/PAPER risk and fills remain unchanged. It emits no orders, approvals or
live readiness. ResearchPosition includes a Phase 19 DerivativeContract, upstream proposal hash,
explicit contracts/leverage/entry/stop, timeframe, horizon and UTC proposal time. No confidence,
Pocket Score, Opportunity Score or forecast probability can supply leverage; extra fields reject.

The sole model is LINEAR_ISOLATED_MARK_NOTIONAL_1: cash-settled linear perpetuals/dated futures,
BASE_UNITS_PER_CONTRACT, identical quote/settlement/reference-index currency, ISOLATED margin,
one flat maintenance-rate tier with explicit maximum mark notional. Options, inverse multipliers,
cross/portfolio/physical margin, currency conversion and expiry within the horizon reject.
It is a versioned **conditional model**, not a supported venue liquidation implementation.
No derivative provider, automatic ingestion, network calls or startup workers are introduced.

Inputs are immutable caller-supplied research records with provenance hashes, versions and causal
timestamps. PortfolioCollateral declares equity, net free collateral and settlement currency.
PriorRiskCheck is an offline attestation bound to the complete position and portfolio hashes;
it is not authenticated order approval. MarginAssumptions bind the complete contract hash,
initial/maintenance/fee rates, tier ceiling, validity through the declared horizon and rules reference.
HorizonVolatility must explicitly normalize volatility as a horizon-return fraction and bind contract,
timeframe/horizon/origin. TransactionAssumptions bind contract/horizon and fee/spread/slippage plus
an adverse funding fraction over that entire horizon. No annualization or funding-period conversion
is guessed. REAL labels/hashes are caller assertions, not independently authenticated market records;
synthetic assertions cannot become financial validation. Callers must supply legitimately derived data.

Missing, stale, future, mixed-origin, wrong currency, incompatible horizon/contract/risk hashes,
failed/expired/noncausal prior risk, expired margin rules or invalid reserve rates reject before
numerical results are generated. Structurally malformed DTOs reject with ValidationError; a cutoff
later than the actual clock rejects with ValueError. No absent metric is replaced by plausible data.

## Financial equations and assumptions

Let Q = contracts × base-unit multiplier, E = entry reference mark, N = Q×E, L = explicit leverage,
C = N/L (isolated allocated collateral). Opening execution rate o is entry fee + half-spread +
slippage; closing rate c is exit fee + half-spread + slippage, all normalized from bps. Funding f is
a nonnegative adverse cost fraction of ENTRY notional over the horizon. Fees and funding consume C;
this is a research convention, not an actual account debit/fill. Available collateral must cover C.
Initial margin requires 1/L ≥ initial rate. The configured collateral/equity and notional caps apply.

With maintenance rate m and liquidation fee rate l, assume maintenance/reserve = (m+l+c)×Q×mark.
Remaining collateral A = C − N×(o+f). Solve equity = maintenance + modeled closing/liquidation reserve:

- LONG: P_liq = max(0, (N−A)/(Q×(1−m−l−c))).
- SHORT: P_liq = max(0, (N+A)/(Q×(1+m+l+c))).

A nonpositive adverse liquidation distance means initial margin is exhausted. LONG stops must be
below E; SHORT stops above E. Distance to liquidation must exceed stop distance plus the explicitly
configured buffer. Tier applicability must cover entry, modeled liquidation and scenario mark
notionals; crossing that ceiling rejects rather than inventing dynamic maintenance tiers/deductions.
All arithmetic uses Decimal in a private 160-digit ROUND_HALF_EVEN context (bounded inputs allow
triple products); ratio outputs are conditional research values, not exchange tick/settlement rounding.

Modeled baseline stop loss = Q×abs(E−stop) + N×(o+f) + Q×stop×c. Expected transaction costs are those
explicit assumed costs at the declared stop, not an empirical expectation. No guaranteed stop fill
or loss cap is inferred. All six stress families are mandatory, named uniquely and explicitly
parameterized. Gap, volatility, slippage and correlated families must actually exercise their knob;
perpetual funding stress must add an adverse funding shock. Dated futures reject funding assumptions
and their mandatory funding scenario is explicitly not applicable (zero funding); other carry costs
are unsupported.

For each scenario, adverse move = max(stop distance, gap + horizon volatility×shock multiple).
Forced LIQUIDATION uses at least 1/L + the explicit overshoot: a fixed gross-margin-loss benchmark,
independent of cost-dependent liquidation thresholds. LONG marks floor at zero; SHORT adverse marks
have no zero-price cap on losses. Additional slippage is charged on opening AND closing and updates
both collateral and closing reserve; additional funding updates the liquidation threshold.

Scenario transaction costs = N×(o+extra_slip) + Q×exit_mark×(c+extra_slip+liquidation_fee_if_triggered).
Funding cost = N×(f+extra_funding). Position loss = Q×abs(E−exit_mark) + transaction + funding costs.
A liquidation flag records crossing the conditional threshold, not a fabricated fill at that price.
Gap exit marks can produce loss greater than C; collateral deficit = max(0, position loss−C).
No insurance fund, limited liability, ADL or automatic margin replenishment is presumed.

Correlated loss is the explicit scenario fraction of starting portfolio equity for OTHER holdings,
excluding the proposed position. Combined loss adds position and other-holding loss; projected equity
may be negative. Maximum modeled loss is the maximum of baseline stop loss and combined declared
scenario losses; portfolio risk fraction divides it by starting equity. This finite scenario maximum
is not a worst-case bound over all future paths. A ruin_scenario flags projected equity ≤0; validated
ruin probability is unavailable and always null. No stress has an invented frequency/probability.

## Status, immutability and usage

Explicit LeveragePolicy supplies leverage/notional/collateral caps, ordered ELEVATED/HIGH_RISK/hard
loss bands, input age, stop buffer, overshoot and whether to reject standard-scenario liquidation
or collateral deficits. Mandatory forced liquidation is a survival benchmark; it does not alone
reject a position if policy tolerates its modeled capital contribution/deficit. Hard loss/tier/
readiness failures or any modeled portfolio ruin yield REJECTED with exact reason codes. Otherwise
status follows the configured maximum combined loss fraction. ACCEPTABLE is a conditional research
classification, never financial qualification, sizing advice or authorization.

LeverageAssessment retains the full request, deterministic input-addressed UUID, input/content hashes,
actual generation time, all stress loss/cost/funding/deficit/ruin/tier details and explicit warnings.
All accepted/rejected outputs have mode RESEARCH_ONLY, execution_authorized=false, live_ready=false,
ruin_probability=null. Hash/identity/time/status validators prevent accidental corruption, but are
not cryptographic signatures or independent recomputation against untrusted forged reports.
There is no database persistence, migration, API, UI, broker integration or execution consumer.


Adding Python modules changes the existing global source-tree hash. Previous PAPER accounts remain
readable/replayable, but their readiness becomes RUNTIME_IDENTITY_CHANGED and new processing refuses
the old runtime identity. No header/checkpoint/model proof is rewritten to bypass this safety guard;
continued research needs a new current-identity run/account and matching qualification. This is a
compatibility consequence, not a database migration or newly authorized execution route.

## References and research debt

Official venue documentation demonstrates that mark price, maintenance tiers, closing fees and
margin mode matter: [Bybit liquidation process](https://www.bybit.com/en/help-center/article/UTA-Trading-Rules-Liquidation-Process?tabIndex=2)
and [2025 margin calculation adjustment](https://www.bybit-global.com/en/help-center/article/Understanding-the-Adjustment-and-Impact-of-the-New-Margin-Calculation?category=cd60af6303161fd598).
These are context references, not the source of a claimed live venue formula. The equations above
are independently derived from the explicitly declared isolated-equity model.

Debt: genuine derivative/funding/mark data and measured volatility, authenticated prior risk and
collateral reconciliation, venue-specific tiers/deductions/fees/rounding/liquidation/ADL, collateral
haircuts/peg stress, dynamic cross-margin/correlations, actual stop execution and path-dependent
funding, inverse/options models, empirical OOS/holdout/shadow validation and ruin estimation.
No production readiness or profitability is claimed. Phase 26 read-only connectivity is next;
Phase 25 cannot enable leveraged spot, derivatives or live execution.
