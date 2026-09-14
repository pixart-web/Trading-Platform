import { describe, expect, it } from "vitest";
import { horizons } from "../lib/analysis";
import {
  alertSchema, snapshotProblem, snapshotSchema, watchlistProblem, watchlistSchema,
} from "../lib/watchlists";

const list = watchlistSchema.parse({
  schema_version: "watchlist-1.0.0", watchlist_id: "11111111-1111-4111-8111-000000000101",
  name: "Principais", revision: 2, created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T01:00:00Z", members: [{
    member_id: "11111111-1111-4111-8111-000000000102", market_id: "test-market",
    asset_id: "test-asset", candle_timeframe: "1h", added_at: "2025-01-01T01:00:00Z",
  }],
});
const snapshot = snapshotSchema.parse({
  schema_version: "watchlist-snapshot-1.0.0",
  snapshot_id: "11111111-1111-4111-8111-000000000103", watchlist_id: list.watchlist_id,
  watchlist_revision: 2, as_of: "2025-01-01T02:00:00Z", generated_at: "2025-01-01T03:00:00Z",
  status: "UNAVAILABLE", input_hash: "a".repeat(64), items: [{
    ...list.members[0], report_id: null, report_status: null,
    unavailable_reason: "NO_ANALYSIS_SNAPSHOT",
    horizons: horizons.map(horizon => ({ horizon, conclusion: "UNAVAILABLE" })),
  }],
});

describe("watchlist contracts", () => {
  it("accepts a canonical list and exact unavailable snapshot", () => {
    expect(watchlistProblem(list)).toBeNull();
    expect(snapshotProblem(snapshot, list)).toBeNull();
  });
  it("rejects malformed identifiers and reordered horizons", () => {
    expect(() => watchlistSchema.parse({ ...list, watchlist_id: "not-a-uuid" })).toThrow();
    const changed = structuredClone(snapshot);
    changed.items[0].horizons.reverse();
    expect(snapshotProblem(changed, list)).toContain("canónicos");
  });
  it("rejects unexplained availability and future list revision", () => {
    const unexplained = structuredClone(snapshot);
    unexplained.items[0].report_id = "11111111-1111-4111-8111-000000000104";
    expect(snapshotProblem(unexplained, list)).toContain("disponibilidade");
    expect(snapshotProblem({ ...snapshot, watchlist_revision: 3 }, list)).toContain("versão");
  });
  it("validates explained alert events", () => {
    const event = alertSchema.parse({
      schema_version: "watchlist-alert-1.0.0", event_id: "11111111-1111-4111-8111-000000000105",
      watchlist_id: list.watchlist_id, snapshot_id: snapshot.snapshot_id,
      previous_snapshot_id: "11111111-1111-4111-8111-000000000106",
      member_id: list.members[0].member_id, market_id: "test-market", candle_timeframe: "1h",
      horizon: "1H", event_type: "HORIZON_CONCLUSION_CHANGED",
      previous_conclusion: "NO_TRADE", current_conclusion: "ELIGIBLE_LONG",
      observed_at: snapshot.as_of, created_at: snapshot.generated_at,
      reason: "ANALYZE_CONCLUSION_TRANSITION",
    });
    expect(event.current_conclusion).toBe("ELIGIBLE_LONG");
  });
});