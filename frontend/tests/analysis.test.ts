import { describe, expect, it } from "vitest";
import { analysisProblem, analysisResponseSchema, horizons } from "../lib/analysis";

const asOf = "2025-01-01T02:00:00Z";
const missingHorizon = (horizon: typeof horizons[number]) => ({
  horizon, status: "UNAVAILABLE" as const, conclusion: "UNAVAILABLE" as const,
  issues: ["FORECAST_NOT_PRODUCED", "DIRECTIONAL_NOT_PRODUCED", "OPPORTUNITY_NOT_PRODUCED"],
  forecast: null, forecast_unavailable_reason: "FORECAST_NOT_PRODUCED",
  directional: null, directional_unavailable_reason: "DIRECTIONAL_NOT_PRODUCED",
  opportunity: null, opportunity_unavailable_reason: "OPPORTUNITY_NOT_PRODUCED",
});
const report = {
  report_id: "00000000-0000-0000-0000-000000000001", market_id: "test-market",
  asset_id: "test-asset", candle_timeframe: "1h" as const, as_of: asOf,
  generated_at: "2025-01-01T03:00:00Z", status: "UNAVAILABLE" as const,
  report_version: "analyze-v1", input_hash: "a".repeat(64),
  issues: ["POCKET_SCORE_NOT_PRODUCED"], pocket_score: null,
  pocket_score_unavailable_reason: "POCKET_SCORE_NOT_PRODUCED",
  horizons: horizons.map(missingHorizon),
};

describe("Analyze response", () => {
  it("accepts an honest missing snapshot", () => {
    const value = analysisResponseSchema.parse({
      schema_version: "analyze-response-1.0.0", market_id: "test-market",
      candle_timeframe: "1h", requested_as_of: asOf, status: "UNAVAILABLE",
      report: null, unavailable_reason: "NO_ANALYSIS_SNAPSHOT",
    });
    expect(value.status).toBe("UNAVAILABLE");
    expect(analysisProblem(value, "test-market", "1h", asOf)).toBeNull();
  });

  it("accepts all canonical horizons without inventing absent artifacts", () => {
    const value = analysisResponseSchema.parse({
      schema_version: "analyze-response-1.0.0", market_id: "test-market",
      candle_timeframe: "1h", requested_as_of: asOf, status: "AVAILABLE",
      report, unavailable_reason: null,
    });
    expect(value.status).toBe("AVAILABLE");
    expect(analysisProblem(value, "test-market", "1h", asOf)).toBeNull();
    if (value.status === "AVAILABLE") expect(value.report.horizons).toHaveLength(13);
  });

  it("blocks reordered horizons and mismatched report identity", () => {
    const reordered = analysisResponseSchema.parse({
      schema_version: "analyze-response-1.0.0", market_id: "test-market",
      candle_timeframe: "1h", requested_as_of: asOf, status: "AVAILABLE",
      report: { ...report, horizons: [...report.horizons].reverse() }, unavailable_reason: null,
    });
    expect(analysisProblem(reordered, "test-market", "1h", asOf)).toContain("horizontes");
    const mismatched = analysisResponseSchema.parse({
      schema_version: "analyze-response-1.0.0", market_id: "test-market",
      candle_timeframe: "1h", requested_as_of: asOf, status: "AVAILABLE",
      report: { ...report, market_id: "other-market" }, unavailable_reason: null,
    });
    expect(analysisProblem(mismatched, "test-market", "1h", asOf)).toContain("identidade");
  });

  it("rejects malformed hashes and plausible values in an unavailable envelope", () => {
    expect(() => analysisResponseSchema.parse({
      schema_version: "analyze-response-1.0.0", market_id: "test-market",
      candle_timeframe: "1h", requested_as_of: asOf, status: "AVAILABLE",
      report: { ...report, input_hash: "bad" }, unavailable_reason: null,
    })).toThrow();
    expect(() => analysisResponseSchema.parse({
      schema_version: "analyze-response-1.0.0", market_id: "test-market",
      candle_timeframe: "1h", requested_as_of: asOf, status: "UNAVAILABLE",
      report, unavailable_reason: "NO_ANALYSIS_SNAPSHOT",
    })).toThrow();
  });
});
