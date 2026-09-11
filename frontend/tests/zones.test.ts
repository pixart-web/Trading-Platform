import { describe, expect, it } from "vitest";
import { zoneSchema, zoneSnapshotSchema, zoneProblem, zoneTimes } from "../lib/zones";
import { upstreamURL } from "../lib/proxy";

const stamp = (hour: number) => new Date(Date.UTC(2025, 0, 1, hour)).toISOString();
const zone = {
  zone_id: "test", role: "SUPPORT", lower: "9", center: "10", upper: "11",
  first_seen: stamp(2), visible_from: stamp(2), last_seen: stamp(3),
  pivot_count: 1, contacts: 0, rejections: 0, flips: 0, age_bars: 1,
  strength: 30, components: { pivots: 10, contacts: 0, rejections: 0, recency: 20 },
  confidence: null, confidence_reason: "UNCALIBRATED",
};
const candles = Array.from({ length: 4 }, (_, i) => ({ market_id: "test", timeframe: "1h" as const,
  open_time: stamp(i), close_time: stamp(i + 1), received_at: stamp(i + 1), source: "fixture",
  open: "10", close: "10", high: "11", low: "9", volume: "0" }));
const snapshot = { engine_version: "zones-1.0.0", spec: { version: "1.0.0" },
  market_id: "test", timeframe: "1h", source: "fixture", input_start: stamp(0), input_count: 4,
  input_hash: "a".repeat(64), bar_close: stamp(4), available_at: stamp(4), zones: [zone] };

describe("zones runtime boundary", () => {
  it("accepts exact decimal bounds and rejects invented probabilities", () => {
    expect(zoneSchema.safeParse(zone).success).toBe(true);
    expect(zoneSchema.safeParse({ ...zone, confidence: 0.8 }).success).toBe(false);
    expect(zoneSchema.safeParse({ ...zone, lower: "NaN" }).success).toBe(false);
    expect(zoneSchema.safeParse({ ...zone, lower: "1e10000000" }).success).toBe(false);
    expect(zoneSchema.safeParse({ ...zone, strength: 100 }).success).toBe(false);
    expect(zoneSchema.safeParse({ ...zone, lower: "11", upper: "9" }).success).toBe(false);
    expect(zoneSchema.safeParse({ ...zone, lower: "1", center: "1.000000000000000001",
      upper: "1.000000000000000002" }).success).toBe(true);
    expect(zoneSchema.safeParse({ ...zone, lower: "1.000000000000000002", center: "1.000000000000000001",
      upper: "1.000000000000000003" }).success).toBe(false);
  });
  it("matches the single response's candle provenance", () => {
    const value = zoneSnapshotSchema.parse(snapshot);
    const range = { start: stamp(0), end: stamp(4) };
    expect(zoneProblem(value, candles, "test", "1h", range)).toBeNull();
    for (const change of [{ market_id: "wrong" }, { source: "wrong" }, { input_count: 3 },
      { available_at: stamp(3) }, { bar_close: stamp(5) }, { zones: [value.zones[0], value.zones[0]] }]) {
      expect(zoneProblem({ ...value, ...change }, candles, "test", "1h", range)).not.toBeNull();
    }
  });
  it("does not backdate chart overlays or draw late imports over historical bars", () => {
    const value = zoneSchema.parse(zone);
    expect(zoneTimes(value, candles)).toEqual([Date.parse(stamp(2)) / 1000, Date.parse(stamp(3)) / 1000]);
    expect(zoneTimes({ ...value, visible_from: stamp(5) }, candles)).toBeNull();
    expect(zoneTimes({ ...value, visible_from: stamp(3) }, candles)).toBeNull();
  });
  it("allows only the bounded zone resource in the gateway", () => {
    expect(upstreamURL(["markets", "test", "zones"], new URLSearchParams("timeframe=1h&token=secret"),
      "http://localhost:8000").pathname).toBe("/api/v1/markets/test/zones");
    expect(() => upstreamURL(["markets", "..", "zones"], new URLSearchParams(), "http://localhost:8000")).toThrow();
  });
});
