import { describe, it, expect, vi, afterEach } from "vitest";
import {
  chartProblem, recentRange, validateRange, responseSchema, candleSchema, readJSON, timeframes,
} from "../lib/market-data";
import { upstreamURL } from "../lib/proxy";

// Synthetic data for deterministic tests only.
const range = { start: "2025-01-01T00:00:00Z", end: "2025-01-01T01:00:00Z" };
const candle = {
  market_id: "test", timeframe: "1h", open_time: range.start, close_time: range.end,
  received_at: range.end, source: "fixture", open: "100.123456789123456789",
  high: "110", low: "90", close: "101", volume: "2.123456789123456789",
};
const payload = {
  candles: [candle], quality: { valid: true, severity: "OK", reason_codes: [], warnings: [],
    timestamp: "2025-01-02T00:00:00Z", source: "fixture", affected_records: [], missing_intervals: [] },
  truncated: false, next_start: null,
};
afterEach(() => vi.unstubAllGlobals());

describe("view contracts", () => {
  it("preserves original decimal strings", () => {
    const parsed = responseSchema.parse(payload);
    expect(parsed.candles[0].open).toBe(candle.open);
    expect(chartProblem(parsed, "test", "1h", range)).toBeNull();
  });
  it.each([{ high: "1" }, { close: "NaN" }, { open: "0" }, { volume: "-1" },
    { open_time: "2025-01-01T00:00:00" }, { close_time: range.start }, { received_at: range.start },
    { close: "1e999" }, { open: "1e-999" }])("rejects malformed prices/timestamps %o", change => {
    expect(candleSchema.safeParse({ ...candle, ...change }).success).toBe(false);
  });
  it("keeps quality rejection, truncation and gaps visible", () => {
    for (const changed of [
      { ...payload, truncated: true },
      { ...payload, quality: { ...payload.quality, valid: false, reason_codes: ["STALE_DATA"] } },
      { ...payload, quality: { ...payload.quality, missing_intervals: [range.start] } },
    ]) expect(chartProblem(responseSchema.parse(changed), "test", "1h", range)).not.toBeNull();
  });
  it("rejects wrong identity, timeframe, source and duplicate data", () => {
    const parsed = responseSchema.parse(payload);
    expect(chartProblem(parsed, "other", "1h", range)).not.toBeNull();
    expect(chartProblem(parsed, "test", "4h", range)).not.toBeNull();
    expect(chartProblem({ ...parsed, candles: [...parsed.candles, ...parsed.candles] }, "test", "1h", range)).not.toBeNull();
    expect(chartProblem({ ...parsed, quality: { ...parsed.quality, source: "wrong" } }, "test", "1h", range)).not.toBeNull();
    expect(chartProblem(parsed, "test", "1h", { ...range, end: "2025-01-01T02:00:00Z" })).not.toBeNull();
  });
  it.each(timeframes)("builds a bounded complete range for %s", timeframe => {
    expect(validateRange(recentRange(timeframe, Date.UTC(2026, 8, 10)), timeframe)).toBeNull();
  });
  it("anchors weekly windows to Monday UTC", () => {
    expect(new Date(recentRange("1w").end).getUTCDay()).toBe(1);
  });
  it("rejects invalid ranges", () => {
    for (const changed of [{ ...range, end: range.start }, { ...range, end: "invalid" },
      { ...range, end: "2025-01-01T01:01:00Z" }, { ...range, end: "2026-01-01T00:00:00Z" }]) {
      expect(validateRange(changed, "1h")).not.toBeNull();
    }
  });
  it("propagates network and malformed response failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 503 })));
    await expect(readJSON("/test", responseSchema)).rejects.toThrow("consultar");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ incorrect: true })));
    await expect(readJSON("/test", responseSchema)).rejects.toThrow("formato");
  });
});

describe("read-only upstream boundary", () => {
  it("forwards only allowed queries to a configured origin", () => {
    const url = upstreamURL(["markets", "test", "candles"],
      new URLSearchParams("timeframe=1h&url=https://evil.example&token=secret"), "http://api:8000");
    expect(url.origin).toBe("http://api:8000");
    expect(url.search).toBe("?timeframe=1h");
  });
  it.each([["orders"], ["assets", ".."], ["markets", "a/b", "candles"], ["health", "ready"]].map(path => ({ path })))(
    "blocks arbitrary paths $path", ({ path }) => {
      expect(() => upstreamURL(path, new URLSearchParams(), "http://api:8000")).toThrow();
    });
  it.each(["file:///etc/passwd", "https://user:pass@example.com", "https://example.com/path"])(
    "blocks invalid server origins %s", base => {
      expect(() => upstreamURL(["assets"], new URLSearchParams(), base)).toThrow();
    });
});
