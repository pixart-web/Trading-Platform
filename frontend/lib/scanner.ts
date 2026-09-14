import { z } from "zod";
import { horizons } from "./analysis";

const stamp = z.iso.datetime({ offset: true });
const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const decimal = z.string().regex(/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/)
  .refine(value => Number.isFinite(Number(value)), "Decimal inválido");
const timeframe = z.enum(["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]);
const direction = z.enum(["LONG", "SHORT"]);
const marketSchema = z.object({
  market_id: z.string().min(1), asset_id: z.string().min(1), symbol: z.string().min(1),
  name: z.string().min(1), asset_type: z.enum(["CRYPTO", "STOCK", "ETF", "INDEX"]),
  venue_id: z.string().min(1), quote_currency: z.string().regex(/^[A-Z0-9]{2,12}$/),
});
const economicsSchema = z.object({
  directional_probability: decimal, directional_expected_return: decimal, expected_move: decimal,
  reward_return: decimal, loss_return: decimal, risk_reward: decimal, total_cost_rate: decimal,
  net_expected_return: decimal, liquidity: decimal, uncertainty: decimal,
});
const componentSchema = z.object({
  component: z.enum(["NET_EDGE", "DIRECTIONAL_PROBABILITY", "EXPECTED_MOVE", "COST_EFFICIENCY",
    "LIQUIDITY", "UNCERTAINTY", "RISK_REWARD"]), raw_value: decimal, normalized_score: decimal,
  configured_weight: decimal, effective_weight: decimal, contribution: decimal,
});
export const scannerOpportunitySchema = z.object({
  schema_version: z.literal("opportunity-score-1.0.0"), opportunity_id: uuid,
  market_id: z.string(), asset_id: z.string(), candle_timeframe: timeframe,
  horizon: z.enum(horizons), as_of: stamp, generated_at: stamp, direction: direction.nullable(),
  status: z.enum(["AVAILABLE", "UNAVAILABLE"]), eligible: z.boolean().nullable(),
  unavailable_reason: z.string().nullable(), exclusion_reasons: z.array(z.string()).max(7),
  score: decimal.nullable(), economics: economicsSchema.nullable(), components: z.array(componentSchema).max(7),
  analysis_id: uuid, forecast_id: uuid, policy_version: z.string(), policy_hash: hash,
  input_hash: hash, cost_version: z.string(),
});
const filtersSchema = z.object({
  asset_types: z.array(z.enum(["CRYPTO", "STOCK", "ETF", "INDEX"])).max(4),
  venue_ids: z.array(z.string()).max(1000), quote_currencies: z.array(z.string()).max(32),
  market_ids: z.array(z.string()).max(1000), directions: z.array(direction).min(1).max(2),
  minimum_score: decimal.nullable(), minimum_net_return: decimal.nullable(),
  minimum_liquidity: decimal.nullable(), maximum_uncertainty: decimal.nullable(),
  minimum_risk_reward: decimal.nullable(), maximum_total_cost: decimal.nullable(),
  max_results_per_policy: z.number().int().min(1).max(250),
});
const rankSchema = z.object({ rank: z.number().int().min(1).max(250), market: marketSchema,
  report_id: uuid, opportunity: scannerOpportunitySchema });
const groupSchema = z.object({ policy_version: z.string(), policy_hash: hash,
  entries: z.array(rankSchema).max(250) });
const exclusionSchema = z.object({ market: marketSchema, report_id: uuid.nullable(),
  opportunity: scannerOpportunitySchema.nullable(), reasons: z.array(z.string()).min(1).max(13) });
export const scanReportSchema = z.object({
  schema_version: z.literal("scan-report-1.0.0"), scan_id: uuid, candle_timeframe: timeframe,
  horizon: z.enum(horizons), as_of: stamp, generated_at: stamp,
  scanner_version: z.literal("scanner-1.0.0"), filters: filtersSchema,
  status: z.enum(["RESULTS", "NO_MATCHES"]), universe_size: z.number().int().min(0).max(1000),
  analyze_reports_found: z.number().int().min(0).max(1000), groups: z.array(groupSchema).max(1000),
  excluded: z.array(exclusionSchema).max(1000), input_hash: hash,
});
export const scanReportsSchema = z.array(scanReportSchema).max(100);
export type ScanReport = z.infer<typeof scanReportSchema>;

export function scanProblem(report: ScanReport, expectedTimeframe: string, horizon: string, asOf: string): string | null {
  if (report.candle_timeframe !== expectedTimeframe || report.horizon !== horizon || report.as_of !== asOf)
    return "O scan não corresponde ao timeframe, horizonte ou instante pedido.";
  const ranked = report.groups.flatMap(group => group.entries);
  const allMarkets = [...ranked.map(entry => entry.market.market_id),
    ...report.excluded.map(item => item.market.market_id)];
  if (ranked.length + report.excluded.length !== report.universe_size
      || new Set(allMarkets).size !== allMarkets.length)
    return "O scan não cobre exatamente o universo declarado.";
  const reportsFound = ranked.length + report.excluded.filter(item => item.report_id !== null).length;
  if (reportsFound !== report.analyze_reports_found)
    return "A cobertura Analyze não corresponde ao conteúdo do scan.";
  if ((ranked.length > 0) !== (report.status === "RESULTS"))
    return "O estado do scan não corresponde aos resultados.";
  for (const group of report.groups) {
    if (group.entries.some((entry, index) => entry.rank !== index + 1
      || entry.opportunity.status !== "AVAILABLE" || entry.opportunity.eligible !== true
      || entry.opportunity.policy_version !== group.policy_version
      || entry.opportunity.policy_hash !== group.policy_hash
      || entry.opportunity.market_id !== entry.market.market_id
      || entry.opportunity.asset_id !== entry.market.asset_id
      || entry.opportunity.candle_timeframe !== report.candle_timeframe
      || entry.opportunity.horizon !== report.horizon || entry.opportunity.as_of !== report.as_of))
      return "Um ranking contém oportunidades incoerentes ou incomparáveis.";
  }
  if (report.excluded.some(item => item.opportunity &&
      (item.opportunity.market_id !== item.market.market_id
        || item.opportunity.asset_id !== item.market.asset_id
        || item.opportunity.candle_timeframe !== report.candle_timeframe
        || item.opportunity.horizon !== report.horizon || item.opportunity.as_of !== report.as_of)))
    return "Uma exclusão contém uma oportunidade com identidade incoerente.";
  return null;
}
