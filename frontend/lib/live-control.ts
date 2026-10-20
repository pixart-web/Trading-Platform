import { z } from "zod";

const decimal = z.string().regex(/^\d+(?:\.\d+)?$/);

export const livePolicySchema = z.object({
  schema_version: z.literal("live-policy-1.0.0"),
  version: z.string(), currency: z.string(),
  capital_limit: decimal, order_notional_limit: decimal, total_exposure_limit: decimal,
  position_notional_limit: decimal, strategy_exposure_limit: decimal,
  broker_exposure_limit: decimal, asset_exposure_limit: decimal, daily_loss_limit: decimal,
  maximum_drawdown: decimal, maximum_leverage: decimal,
  maximum_positions: z.number(), maximum_orders_per_minute: z.number(),
  maximum_orders_per_day: z.number(), maximum_slippage_fraction: decimal,
  maximum_spread_fraction: decimal, maximum_price_deviation_fraction: decimal,
  maximum_data_age_seconds: z.number(), maximum_account_age_seconds: z.number(),
});

export const liveControlSchema = z.object({
  control_id: z.string().uuid(), revision: z.number(),
  mode: z.enum(["OFF", "PAPER", "LIVE_ARMED", "LIVE_ACTIVE", "HALTED", "KILL_SWITCH"]),
  broker: z.enum(["BINANCE", "KUCOIN"]).nullable(),
  market: z.enum(["SPOT", "FUTURES"]).nullable(),
  account_identity_hash: z.string().nullable(), policy: livePolicySchema.nullable(),
  policy_hash: z.string().nullable(), readiness: z.object({
    verified_at: z.string(), credential_qualified: z.boolean(), account_qualified: z.boolean(),
    risk_ready: z.boolean(), strategy_ready: z.boolean(), market_data_healthy: z.boolean(),
    infrastructure_healthy: z.boolean(), reconciliation_healthy: z.boolean(),
    execution_healthy: z.boolean(), source: z.string(), evidence_hash: z.string(),
    schema_version: z.literal("live-readiness-1.0.0"),
  }).nullable(), kill_switch_active: z.boolean(), live_deployment_enabled: z.boolean(),
  derivative_deployment_enabled: z.boolean(), updated_at: z.string(),
});

export type LiveControl = z.infer<typeof liveControlSchema>;

export async function requestLiveControl(method = "GET", body?: object): Promise<LiveControl> {
  const response = await fetch("/api/market-data/live-control", {
    method, cache: "no-store", headers: body ? {
      "Content-Type": "application/json", "X-PA-UI-Request": "live-control",
    } : undefined, body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(payload.detail ?? "Live control unavailable");
  }
  return liveControlSchema.parse(await response.json());
}
