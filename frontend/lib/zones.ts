import { z } from "zod";
import { responseSchema, timeframes, type Candle, type Range, type Timeframe } from "./market-data";

const stamp = z.iso.datetime({ offset: true });
const amount = z.string().max(128).regex(/^\d+(\.\d+)?([eE][+-]?\d+)?$/)
  .refine(v => Number.isFinite(Number(v)) && Number(v) > 0
    && Math.abs(Number(v.split(/[eE]/)[1] ?? 0)) <= 200);

function compare(a: string, b: string): number {
  if (!amount.safeParse(a).success || !amount.safeParse(b).success) return 0;
  const parts = (value: string): [bigint, number] => {
    const [digits, exponent = "0"] = value.split(/[eE]/);
    const [integer, fraction = ""] = digits.split(".");
    return [BigInt(integer + fraction), Number(exponent) - fraction.length];
  };
  const [ai, ae] = parts(a), [bi, be] = parts(b), scale = Math.min(ae, be);
  const delta = ai * 10n ** BigInt(ae - scale) - bi * 10n ** BigInt(be - scale);
  return delta > 0 ? 1 : delta < 0 ? -1 : 0;
}
export const zoneSchema = z.object({
  zone_id: z.string(), role: z.enum(["SUPPORT", "RESISTANCE"]),
  lower: amount, center: amount, upper: amount,
  first_seen: stamp, visible_from: stamp, last_seen: stamp,
  pivot_count: z.number().int().positive(), contacts: z.number().int().nonnegative(),
  rejections: z.number().int().nonnegative(), flips: z.number().int().nonnegative(),
  age_bars: z.number().int().nonnegative(), strength: z.number().int().min(0).max(100),
  confidence: z.null(), confidence_reason: z.literal("UNCALIBRATED"),
  components: z.object({ pivots: z.number().int().min(0).max(40), contacts: z.number().int().min(0).max(30),
    rejections: z.number().int().min(0).max(10), recency: z.number().int().min(0).max(20) }),
}).refine(z => compare(z.lower, z.center) < 0 && compare(z.center, z.upper) < 0
  && Date.parse(z.first_seen) <= Date.parse(z.visible_from)
  && Date.parse(z.visible_from) <= Date.parse(z.last_seen)
  && z.strength === Object.values(z.components).reduce((a, b) => a + b, 0), "Zona incoerente");

export const zoneSnapshotSchema = z.object({
  engine_version: z.literal("zones-1.0.0"),
  spec: z.object({ version: z.literal("1.0.0") }),
  market_id: z.string(), timeframe: z.enum(timeframes), source: z.string(),
  input_start: stamp, input_count: z.number().int().positive().max(1000),
  input_hash: z.string().regex(/^[0-9a-f]{64}$/), bar_close: stamp, available_at: stamp,
  zones: z.array(zoneSchema).max(32),
});
export const zoneResponseSchema = responseSchema.extend({ snapshot: zoneSnapshotSchema });
export type Zone = z.infer<typeof zoneSchema>;
export type ZoneSnapshot = z.infer<typeof zoneSnapshotSchema>;

export function zoneProblem(snapshot: ZoneSnapshot, candles: Candle[], market: string,
  timeframe: Timeframe, range: Range): string | null {
  const last = candles.at(-1);
  const available = Math.max(...candles.map(c => Date.parse(c.received_at)));
  if (!last || snapshot.market_id !== market || snapshot.timeframe !== timeframe
    || snapshot.source !== last.source || snapshot.input_count !== candles.length
    || Date.parse(snapshot.input_start) !== Date.parse(range.start)
    || Date.parse(snapshot.bar_close) !== Date.parse(last.close_time)
    || Date.parse(snapshot.available_at) !== available
    || new Set(snapshot.zones.map(z => z.zone_id)).size !== snapshot.zones.length
    || snapshot.zones.some(z => Date.parse(z.last_seen) > available
      || Date.parse(z.first_seen) < Date.parse(candles[0].close_time))) {
    return "As zonas não correspondem aos dados deste gráfico.";
  }
  return null;
}

/** Drawing begins only on a chart bar at/after actual model availability, never the pivot. */
export function zoneTimes(zone: Zone, candles: Candle[]): [number, number] | null {
  const start = candles.find(c => Date.parse(c.open_time) >= Date.parse(zone.visible_from));
  const end = candles.at(-1);
  return start && end && Date.parse(start.open_time) < Date.parse(end.open_time)
    ? [Date.parse(start.open_time) / 1000, Date.parse(end.open_time) / 1000] : null;
}
