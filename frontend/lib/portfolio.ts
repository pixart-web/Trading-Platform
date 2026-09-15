import { z } from "zod";

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
const stamp = z.iso.datetime({ offset: true });
const decimal = z.string().regex(/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/)
  .refine(value => Number.isFinite(Number(value)), "Decimal inválido");
const timeframe = z.enum(["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]);
const entryType = z.enum(["DEPOSIT", "WITHDRAWAL", "BUY", "SELL"]);

export const portfolioSchema = z.object({
  schema_version: z.literal("portfolio-1.0.0"), portfolio_id: uuid,
  name: z.string().min(1).max(80), base_currency: z.string().regex(/^[A-Z0-9]{2,12}$/),
  accounting_method: z.literal("MOVING_AVERAGE_V1"), valuation_timeframe: timeframe,
  revision: z.number().int().positive(), created_at: stamp, updated_at: stamp,
});
export const portfoliosSchema = z.array(portfolioSchema).max(100);
export const portfolioEntrySchema = z.object({
  schema_version: z.literal("portfolio-entry-1.0.0"), entry_id: uuid, portfolio_id: uuid,
  sequence: z.number().int().positive(), entry_type: entryType, currency: z.string(),
  cash_amount: decimal.nullable(), market_id: z.string().nullable(), asset_id: z.string().nullable(),
  quantity: decimal.nullable(), unit_price: decimal.nullable(), fee: decimal,
  gross_value: decimal, cash_effect: decimal, occurred_at: stamp, recorded_at: stamp,
  note: z.string().max(250).nullable(),
});
export const portfolioEntriesSchema = z.array(portfolioEntrySchema).max(500);
export const portfolioEntryResultSchema = z.object({
  entry: portfolioEntrySchema, portfolio: portfolioSchema,
});
const marketSchema = z.object({
  market_id: z.string(), asset_id: z.string(), symbol: z.string(), name: z.string(),
  asset_type: z.enum(["CRYPTO", "STOCK", "ETF", "INDEX", "FOREX", "COMMODITY", "BOND", "OPTION", "FUTURE"]),
  venue_id: z.string(), quote_currency: z.string(),
});
const positionSchema = z.object({
  market: marketSchema, status: z.enum(["OPEN", "CLOSED"]), quantity: decimal,
  average_cost: decimal, cost_basis: decimal, realized_pnl: decimal,
  last_price: decimal.nullable(), price_time: stamp.nullable(), price_available_at: stamp.nullable(),
  market_value: decimal.nullable(), unrealized_pnl: decimal.nullable(),
});
export const portfolioSnapshotSchema = z.object({
  schema_version: z.literal("portfolio-snapshot-1.0.0"), portfolio_id: uuid,
  portfolio_revision: z.number().int().positive(), ledger_sequence: z.number().int().nonnegative(),
  base_currency: z.string(), accounting_method: z.literal("MOVING_AVERAGE_V1"),
  valuation_timeframe: timeframe, as_of: stamp, generated_at: stamp,
  status: z.enum(["COMPLETE", "PARTIAL"]), cash_balance: decimal, net_contributions: decimal,
  total_fees: decimal, realized_pnl: decimal, positions: z.array(positionSchema).max(250),
  total_cost_basis: decimal, total_market_value: decimal.nullable(),
  unrealized_pnl: decimal.nullable(), equity: decimal.nullable(),
  input_hash: z.string().regex(/^[0-9a-f]{64}$/),
});

export type Portfolio = z.infer<typeof portfolioSchema>;
export type PortfolioEntry = z.infer<typeof portfolioEntrySchema>;
export type PortfolioSnapshot = z.infer<typeof portfolioSnapshotSchema>;
export type EntryType = z.infer<typeof entryType>;

export function portfolioProblem(value: Portfolio): string | null {
  if (value.name !== value.name.trim() || value.updated_at < value.created_at)
    return "A carteira recebida tem metadados incoerentes.";
  return null;
}

export function snapshotProblem(value: PortfolioSnapshot, portfolio: Portfolio): string | null {
  if (value.portfolio_id !== portfolio.portfolio_id
      || value.base_currency !== portfolio.base_currency
      || value.accounting_method !== portfolio.accounting_method
      || value.valuation_timeframe !== portfolio.valuation_timeframe
      || value.portfolio_revision > portfolio.revision)
    return "A avaliação não pertence a esta versão da carteira.";
  const ids = value.positions.map(item => item.market.market_id);
  if (new Set(ids).size !== ids.length || ids.join("|") !== [...ids].sort().join("|"))
    return "As posições não têm uma ordem ou identidade canónica.";
  const missing = value.positions.some(item => item.status === "OPEN" && item.market_value === null);
  if ((missing && value.status !== "PARTIAL") || (!missing && value.status !== "COMPLETE"))
    return "O estado da avaliação não corresponde à cobertura de preços.";
  const totals = [value.total_market_value, value.unrealized_pnl, value.equity];
  if ((missing && totals.some(item => item !== null)) || (!missing && totals.some(item => item === null)))
    return "A avaliação apresenta totais sem cobertura completa.";
  for (const item of value.positions) {
    const pricing = [item.last_price, item.price_time, item.price_available_at,
      item.market_value, item.unrealized_pnl];
    if (item.status === "CLOSED" && pricing.some(field => field !== null))
      return "Uma posição fechada apresenta uma avaliação corrente.";
    if (item.status === "OPEN" && pricing.some(field => field === null)
        && pricing.some(field => field !== null))
      return "Uma posição contém uma avaliação parcial incoerente.";
  }
  return null;
}
