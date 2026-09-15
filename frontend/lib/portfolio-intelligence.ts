import { z } from "zod";
import type { Portfolio } from "@/lib/portfolio";

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
const stamp = z.iso.datetime({ offset: true });
const decimal = z.string().regex(/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/);
const timeframe = z.enum(["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]);
const reason = z.enum([
  "PORTFOLIO_VALUATION_INCOMPLETE", "NO_OPEN_POSITIONS", "INSUFFICIENT_HISTORY",
  "ZERO_VARIANCE", "STALE_VALUATION", "BENCHMARK_NOT_CONFIGURED", "SECTOR_DATA_UNAVAILABLE",
  "LIQUIDITY_DATA_UNAVAILABLE", "NAV_HISTORY_UNAVAILABLE",
  "REGIME_ATTRIBUTION_UNAVAILABLE", "HORIZON_ATTRIBUTION_UNAVAILABLE",
]);
const metric = z.object({
  status: z.enum(["AVAILABLE", "UNAVAILABLE"]), value: decimal.nullable(),
  reason: reason.nullable(), explanation: z.string().min(1),
}).superRefine((value, ctx) => {
  if ((value.status === "AVAILABLE" && (value.value === null || value.reason !== null))
      || (value.status === "UNAVAILABLE" && (value.value !== null || value.reason === null)))
    ctx.addIssue({ code: "custom", message: "Estado da métrica incoerente" });
});
const dimension = z.enum(["CASH", "MARKET", "ASSET_CLASS", "CURRENCY", "VENUE", "DIRECTION"]);
const allocation = z.object({
  dimension, key: z.string().min(1), value: decimal, portfolio_weight: decimal,
});
const concentration = z.object({
  dimension, hhi: metric, largest_weight: metric, effective_count: metric,
});
const marketRisk = z.object({
  market_id: z.string(), observations: z.number().int().nonnegative(),
  per_bar_volatility: metric, beta: metric,
});
const correlation = z.object({
  left_market_id: z.string(), right_market_id: z.string(),
  observations: z.number().int().nonnegative(), correlation: metric,
});
const contribution = z.object({ market_id: z.string(), contribution_fraction: metric });
const policy = z.object({
  schema_version: z.literal("portfolio-intelligence-policy-1.0.0"),
  policy_version: z.literal("portfolio-intelligence-1.0.0"),
  lookback_bars: z.number().int().min(20).max(500),
  minimum_observations: z.number().int().min(3).max(499),
  maximum_price_age_bars: z.number().int().min(1).max(100),
});
export const portfolioIntelligenceSchema = z.object({
  schema_version: z.literal("portfolio-intelligence-report-1.0.0"),
  analysis_id: uuid, portfolio_id: uuid, portfolio_revision: z.number().int().positive(),
  ledger_sequence: z.number().int().nonnegative(), timeframe,
  benchmark_market_id: z.string().nullable(), as_of: stamp, generated_at: stamp,
  status: z.enum(["COMPLETE", "PARTIAL"]), policy,
  policy_hash: z.string().regex(/^[0-9a-f]{64}$/),
  portfolio_input_hash: z.string().regex(/^[0-9a-f]{64}$/),
  equity: decimal.nullable(), allocations: z.array(allocation).max(1000),
  concentrations: z.array(concentration).max(10), market_risk: z.array(marketRisk).max(250),
  correlations: z.array(correlation).max(31125),
  portfolio_per_bar_volatility: metric, portfolio_beta: metric,
  risk_contributions: z.array(contribution).max(250),
  sector_concentration: metric, drawdown: metric, liquidity: metric,
  regime_exposure: metric, horizon_exposure: metric,
  observations: z.array(z.object({
    code: z.string(), severity: z.enum(["INFO", "WARNING"]),
    message: z.string().min(1), evidence: z.array(z.string()).max(20),
  })).max(100),
  input_hash: z.string().regex(/^[0-9a-f]{64}$/),
});
export const portfolioIntelligenceListSchema = z.array(portfolioIntelligenceSchema).max(100);
export type PortfolioIntelligence = z.infer<typeof portfolioIntelligenceSchema>;

export function intelligenceProblem(
  value: PortfolioIntelligence, portfolio: Portfolio,
): string | null {
  if (value.portfolio_id !== portfolio.portfolio_id
      || value.portfolio_revision > portfolio.revision
      || value.timeframe !== portfolio.valuation_timeframe)
    return "A inteligência não pertence a esta versão da carteira.";
  const allocations = value.allocations.map(item => item.dimension + "|" + item.key);
  if (allocations.join(",") !== [...allocations].sort().join(",")
      || new Set(allocations).size !== allocations.length)
    return "As alocações não têm identidade canónica.";
  const risks = value.market_risk.map(item => item.market_id);
  if (risks.join(",") !== [...risks].sort().join(",") || new Set(risks).size !== risks.length)
    return "As métricas de mercado não têm identidade canónica.";
  if (value.correlations.some(item => item.left_market_id >= item.right_market_id))
    return "As correlações não têm pares canónicos.";
  return null;
}
