import { z } from "zod";

const stamp = z.iso.datetime({ offset: true });
const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
const decimal = z.string().regex(/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/)
  .refine(value => Number.isFinite(Number(value)), "Decimal inválido");
export const horizons = ["1H", "4H", "8H", "12H", "24H", "2D", "3D", "7D", "14D", "30D", "90D", "6M", "12M"] as const;
const timeframe = z.enum(["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]);
const identity = {
  market_id: z.string(), asset_id: z.string(), candle_timeframe: timeframe,
};
const probabilitySchema = z.object({
  direction: z.enum(["UP", "DOWN", "RANGE"]), probability: decimal,
});
const forecastSchema = z.object({
  forecast_id: uuid, ...identity, horizon: z.enum(horizons), generated_at: stamp,
  expires_at: stamp, status: z.enum(["AVAILABLE", "UNAVAILABLE"]),
  unavailable_reason: z.string().nullable(), direction: z.enum(["UP", "DOWN", "RANGE"]).nullable(),
  probabilities: z.array(probabilitySchema).max(3), expected_return: decimal.nullable(),
  expected_move: decimal.nullable(), expected_low_return: decimal.nullable(),
  expected_high_return: decimal.nullable(), confidence: decimal.nullable(),
  probability_calibration: z.enum(["CALIBRATED", "UNCALIBRATED"]).nullable(),
  model_version: z.string(), model_stage: z.string(), feature_version: z.string(),
});
const criterionSchema = z.object({
  criterion: z.string(), label: z.string(), status: z.enum(["AVAILABLE", "UNAVAILABLE"]),
  value: decimal.nullable(), passed: z.boolean().nullable(), threshold: decimal,
  operator: z.enum(["GREATER_THAN_OR_EQUAL", "LESS_THAN_OR_EQUAL"]),
  rule_version: z.string(), source_version: z.string(), unavailable_reason: z.string().nullable(),
});
const caseSchema = z.object({
  side: z.enum(["LONG", "SHORT"]), status: z.enum(["COMPLETE", "UNAVAILABLE"]),
  qualifies: z.boolean().nullable(), results: z.array(criterionSchema).max(16),
});
const directionalSchema = z.object({
  analysis_id: uuid, ...identity, horizon: z.enum(horizons), as_of: stamp,
  decision: z.enum(["LONG", "SHORT", "NO_TRADE"]), reason: z.string(),
  policy_version: z.string(), long_case: caseSchema, short_case: caseSchema,
});
const economicsSchema = z.object({
  directional_probability: decimal, directional_expected_return: decimal,
  expected_move: decimal, reward_return: decimal, loss_return: decimal,
  risk_reward: decimal, total_cost_rate: decimal, net_expected_return: decimal,
  liquidity: decimal, uncertainty: decimal,
});
const opportunitySchema = z.object({
  opportunity_id: uuid, analysis_id: uuid, forecast_id: uuid, ...identity,
  horizon: z.enum(horizons), as_of: stamp, status: z.enum(["AVAILABLE", "UNAVAILABLE"]),
  direction: z.enum(["LONG", "SHORT"]).nullable(), eligible: z.boolean().nullable(),
  unavailable_reason: z.string().nullable(), exclusion_reasons: z.array(z.string()).max(7),
  score: decimal.nullable(), economics: economicsSchema.nullable(),
  policy_version: z.string(), cost_version: z.string(),
});
const pocketSchema = z.object({
  score_id: uuid, ...identity, as_of: stamp, status: z.enum(["AVAILABLE", "UNAVAILABLE"]),
  score: decimal.nullable(), unavailable_reason: z.string().nullable(), coverage: decimal,
  score_version: z.string(), components: z.array(z.object({
    component: z.string(), label: z.string(), status: z.enum(["AVAILABLE", "UNAVAILABLE"]),
    raw_value: decimal.nullable(), contribution: decimal.nullable(),
    unavailable_reason: z.string().nullable(), normalization_version: z.string(),
  })).max(16),
});
const horizonSchema = z.object({
  horizon: z.enum(horizons), status: z.enum(["COMPLETE", "PARTIAL", "UNAVAILABLE"]),
  conclusion: z.enum(["ELIGIBLE_LONG", "ELIGIBLE_SHORT", "INELIGIBLE_LONG", "INELIGIBLE_SHORT", "NO_TRADE", "UNAVAILABLE"]),
  issues: z.array(z.string()).max(9), forecast: forecastSchema.nullable(),
  forecast_unavailable_reason: z.string().nullable(), directional: directionalSchema.nullable(),
  directional_unavailable_reason: z.string().nullable(), opportunity: opportunitySchema.nullable(),
  opportunity_unavailable_reason: z.string().nullable(),
});
const reportSchema = z.object({
  report_id: uuid, ...identity, as_of: stamp, generated_at: stamp,
  status: z.enum(["COMPLETE", "PARTIAL", "UNAVAILABLE"]), report_version: z.string(),
  input_hash: z.string().regex(/^[0-9a-f]{64}$/), issues: z.array(z.string()).max(2),
  pocket_score: pocketSchema.nullable(), pocket_score_unavailable_reason: z.string().nullable(),
  horizons: z.array(horizonSchema).length(13),
});
const responseBase = {
  schema_version: z.literal("analyze-response-1.0.0"), market_id: z.string(),
  candle_timeframe: timeframe, requested_as_of: stamp,
};
export const analysisResponseSchema = z.discriminatedUnion("status", [
  z.object({ ...responseBase, status: z.literal("AVAILABLE"), report: reportSchema, unavailable_reason: z.null() }),
  z.object({ ...responseBase, status: z.literal("UNAVAILABLE"), report: z.null(), unavailable_reason: z.string() }),
]);
export type AnalysisResponse = z.infer<typeof analysisResponseSchema>;
export type AnalyzeReport = z.infer<typeof reportSchema>;
export type AnalyzeHorizon = z.infer<typeof horizonSchema>;

export function analysisProblem(
  response: AnalysisResponse, marketId: string, expectedTimeframe: string, asOf: string,
): string | null {
  if (response.market_id !== marketId || response.candle_timeframe !== expectedTimeframe
      || response.requested_as_of !== asOf) return "A análise não corresponde ao mercado, timeframe ou instante pedido.";
  if (response.status === "UNAVAILABLE") return null;
  const report = response.report;
  if (report.market_id !== marketId || report.candle_timeframe !== expectedTimeframe
      || report.as_of !== asOf || report.asset_id.length === 0
      || report.horizons.map(item => item.horizon).join("|") !== horizons.join("|")) {
    return "O snapshot de análise tem identidade ou horizontes incoerentes.";
  }
  for (const item of report.horizons) {
    for (const artifact of [item.forecast, item.directional, item.opportunity]) {
      if (artifact && (artifact.market_id !== marketId || artifact.asset_id !== report.asset_id
          || artifact.candle_timeframe !== expectedTimeframe || artifact.horizon !== item.horizon)) {
        return "Um artefacto não pertence ao snapshot de análise.";
      }
    }
    if (item.directional && item.directional.as_of !== asOf) return "A análise direcional usa outro instante.";
    if (item.opportunity && (item.opportunity.as_of !== asOf
        || item.opportunity.analysis_id !== item.directional?.analysis_id
        || item.opportunity.forecast_id !== item.forecast?.forecast_id)) {
      return "A oportunidade não referencia os artefactos apresentados.";
    }
  }
  return null;
}
