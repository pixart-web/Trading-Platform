import { z } from "zod";

export const timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"] as const;
export type Timeframe = typeof timeframes[number];
export const durations: Record<Timeframe, number> = {
  "1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600,
  "4h": 14400, "1d": 86400, "1w": 604800,
};
const stamp = z.iso.datetime({ offset: true });
const decimal = z.string().regex(/^\d+(\.\d+)?([eE][+-]?\d+)?$/)
  .refine((s) => Number.isFinite(Number(s)) && Number(s) >= 0, "Decimal inválido");
const price = decimal.refine((s) => Number(s) > 0, "Preço inválido");
export const marketSchema = z.object({
  market_id: z.string(), asset_id: z.string(), venue_id: z.string(),
  symbol: z.string(), quote_currency: z.string(),
});
export const assetSchema = z.object({
  asset_id: z.string(), symbol: z.string(), name: z.string(), asset_type: z.string(),
});
export type Market = z.infer<typeof marketSchema>;
export const candleSchema = z.object({
  market_id: z.string(), timeframe: z.enum(timeframes), open_time: stamp, close_time: stamp,
  received_at: stamp, source: z.string(),
  open: price, high: price, low: price, close: price, volume: decimal,
}).refine((c) => Number(c.low) <= Math.min(Number(c.open), Number(c.close))
  && Number(c.high) >= Math.max(Number(c.open), Number(c.close))
  && Date.parse(c.close_time) - Date.parse(c.open_time) === durations[c.timeframe] * 1000
  && Date.parse(c.received_at) >= Date.parse(c.close_time), "Candle incoerente");
export type Candle = z.infer<typeof candleSchema>;
export const responseSchema = z.object({
  candles: z.array(candleSchema).max(1000),
  quality: z.object({
    valid: z.boolean(), severity: z.enum(["OK", "ERROR"]), reason_codes: z.array(z.string()),
    warnings: z.array(z.string()), timestamp: stamp, source: z.string(),
    affected_records: z.array(z.number().int().nonnegative()), missing_intervals: z.array(stamp),
  }),
  truncated: z.boolean(), next_start: stamp.nullable(),
});
export type CandleResponse = z.infer<typeof responseSchema>;
export type Range = { start: string; end: string };

export function recentRange(timeframe: Timeframe, now = Date.now()): Range {
  const width = durations[timeframe] * 1000;
  const anchor = timeframe === "1w" ? Date.UTC(1970, 0, 5) : 0;
  const end = Math.floor((now - anchor) / width) * width + anchor;
  return { start: new Date(end - 200 * width).toISOString(), end: new Date(end).toISOString() };
}

export function validateRange(range: Range, timeframe: Timeframe): string | null {
  const start = Date.parse(range.start), end = Date.parse(range.end);
  const slots = (end - start) / (durations[timeframe] * 1000);
  if (!Number.isFinite(slots) || slots <= 0) return "O fim deve ser posterior ao início.";
  if (!Number.isInteger(slots)) return "O período deve conter candles completos deste timeframe.";
  if (slots > 1000) return "Seleciona até 1 000 candles por consulta.";
  return null;
}

/** View-only trust gate. Never repairs, sorts, fills or overrides a rejected backend result. */
export function chartProblem(data: CandleResponse, marketId: string, timeframe: Timeframe, range: Range): string | null {
  if (data.truncated) return "Resposta parcial. Reduz o período para ver uma série completa.";
  if (!data.quality.valid || data.quality.severity !== "OK"
    || data.quality.reason_codes.length || data.quality.missing_intervals.length) {
    return "Os dados não passaram a verificação de qualidade.";
  }
  let previous = -Infinity;
  for (const c of data.candles) {
    const time = Date.parse(c.open_time);
    if (c.market_id !== marketId || c.timeframe !== timeframe || time <= previous
      || c.source !== data.quality.source || Date.parse(c.received_at) > Date.parse(data.quality.timestamp)
      || time < Date.parse(range.start) || Date.parse(c.close_time) > Date.parse(range.end)) {
      return "A resposta não corresponde ao mercado, período ou ordem esperados.";
    }
    previous = time;
  }
  const slots = (Date.parse(range.end) - Date.parse(range.start)) / (durations[timeframe] * 1000);
  if (data.candles.length && (data.candles.length !== slots || data.candles.some(
    (c, index) => Date.parse(c.open_time) !== Date.parse(range.start) + index * durations[timeframe] * 1000
  ))) return "A série contém intervalos em falta.";
  return null;
}

export const qualityLabels: Record<string, string> = {
  MISSING_INTERVAL: "Intervalos em falta", STALE_DATA: "Dados desatualizados",
  OUT_OF_ORDER: "Observações fora de ordem", DUPLICATE_RECORD: "Observações duplicadas",
  INVALID_OHLC: "Preços incoerentes", INVALID_PRICE: "Preço inválido",
  INVALID_TIMESTAMP: "Timestamp inválido", INVALID_VOLUME: "Volume inválido",
  MALFORMED_VALUE: "Valor malformado", UNEXPECTED_RECORD: "Observação inesperada",
};

export async function readJSON<T>(url: string, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(12000);
  const response = await fetch(url, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout, cache: "no-store" });
  if (!response.ok) throw new Error(response.status === 404
    ? "O mercado já não está disponível." : "Não foi possível consultar os dados de mercado.");
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) throw new Error("O serviço devolveu dados num formato inválido.");
  return parsed.data;
}
