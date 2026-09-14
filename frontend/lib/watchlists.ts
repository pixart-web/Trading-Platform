import { z } from "zod";
import { horizons } from "@/lib/analysis";

const uuid = z.string().uuid();
const stamp = z.iso.datetime({ offset: true });
const timeframe = z.enum(["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]);
const conclusion = z.enum(["ELIGIBLE_LONG", "ELIGIBLE_SHORT", "INELIGIBLE_LONG",
  "INELIGIBLE_SHORT", "NO_TRADE", "UNAVAILABLE"]);
const memberSchema = z.object({
  member_id: uuid, market_id: z.string(), asset_id: z.string(), candle_timeframe: timeframe,
  added_at: stamp,
});
export const watchlistSchema = z.object({
  schema_version: z.literal("watchlist-1.0.0"), watchlist_id: uuid,
  name: z.string().min(1).max(80), revision: z.number().int().positive(),
  created_at: stamp, updated_at: stamp, members: z.array(memberSchema).max(250),
});
export const watchlistsSchema = z.array(watchlistSchema).max(100);
const horizonStateSchema = z.object({ horizon: z.enum(horizons), conclusion });
const snapshotItemSchema = z.object({
  member_id: uuid, market_id: z.string(), asset_id: z.string(), candle_timeframe: timeframe,
  report_id: uuid.nullable(), report_status: z.enum(["COMPLETE", "PARTIAL", "UNAVAILABLE"]).nullable(),
  unavailable_reason: z.string().nullable(), horizons: z.array(horizonStateSchema).length(13),
});
export const snapshotSchema = z.object({
  schema_version: z.literal("watchlist-snapshot-1.0.0"), snapshot_id: uuid,
  watchlist_id: uuid, watchlist_revision: z.number().int().positive(), as_of: stamp,
  generated_at: stamp, status: z.enum(["COMPLETE", "PARTIAL", "UNAVAILABLE"]),
  input_hash: z.string().regex(/^[0-9a-f]{64}$/), items: z.array(snapshotItemSchema).max(250),
});
export const nullableSnapshotSchema = snapshotSchema.nullable();
export const alertSchema = z.object({
  schema_version: z.literal("watchlist-alert-1.0.0"), event_id: uuid, watchlist_id: uuid,
  snapshot_id: uuid, previous_snapshot_id: uuid, member_id: uuid, market_id: z.string(),
  candle_timeframe: timeframe, horizon: z.enum(horizons).nullable(),
  event_type: z.enum(["ANALYSIS_BECAME_AVAILABLE", "ANALYSIS_BECAME_UNAVAILABLE",
    "HORIZON_CONCLUSION_CHANGED"]), previous_conclusion: conclusion.nullable(),
  current_conclusion: conclusion.nullable(), observed_at: stamp, created_at: stamp,
  reason: z.string(),
});
export const alertsSchema = z.array(alertSchema).max(500);
export const snapshotResultSchema = z.object({ snapshot: snapshotSchema, events: alertsSchema });

export type Watchlist = z.infer<typeof watchlistSchema>;
export type WatchlistSnapshot = z.infer<typeof snapshotSchema>;
export type WatchlistAlert = z.infer<typeof alertSchema>;

export function watchlistProblem(value: Watchlist): string | null {
  if (new Set(value.members.map(item => item.market_id)).size !== value.members.length) {
    return "A lista contém mercados repetidos.";
  }
  return null;
}

export function snapshotProblem(value: WatchlistSnapshot, list: Watchlist): string | null {
  if (value.watchlist_id !== list.watchlist_id || value.watchlist_revision > list.revision) {
    return "O snapshot não pertence a esta versão da lista.";
  }
  for (const item of value.items) {
    if (item.horizons.map(entry => entry.horizon).join("|") !== horizons.join("|")) {
      return "Um mercado não contém os horizontes canónicos.";
    }
    if ((item.report_id === null) === (item.unavailable_reason === null)) {
      return "Um mercado não explica a disponibilidade da análise.";
    }
  }
  return null;
}