import { describe, expect, it } from "vitest";
import { scanProblem, scanReportSchema } from "../lib/scanner";

const asOf = "2025-01-01T00:00:00Z";
const base = {
  schema_version: "scan-report-1.0.0" as const,
  scan_id: "00000000-0000-4000-8000-000000000800", candle_timeframe: "1h" as const,
  horizon: "24H" as const, as_of: asOf, generated_at: "2025-01-01T01:00:00Z",
  scanner_version: "scanner-1.0.0" as const,
  filters: { asset_types: [], venue_ids: [], quote_currencies: [], market_ids: [],
    directions: ["LONG", "SHORT"] as const, minimum_score: null, minimum_net_return: null,
    minimum_liquidity: null, maximum_uncertainty: null, minimum_risk_reward: null,
    maximum_total_cost: null, max_results_per_policy: 100 },
  status: "NO_MATCHES" as const, universe_size: 1, analyze_reports_found: 0, groups: [],
  excluded: [{ market: { market_id: "test-market", asset_id: "test-asset", symbol: "TEST",
    name: "Test Asset", asset_type: "STOCK" as const, venue_id: "test-venue", quote_currency: "EUR" },
    report_id: null, opportunity: null, reasons: ["NO_ANALYZE_REPORT"] }], input_hash: "a".repeat(64),
};

describe("scanner report", () => {
  it("accepts an honest no-match universe with explicit exclusions", () => {
    const report = scanReportSchema.parse(base);
    expect(scanProblem(report, "1h", "24H", asOf)).toBeNull();
    expect(report.excluded[0].reasons).toEqual(["NO_ANALYZE_REPORT"]);
  });

  it("detects identity and universe inconsistencies", () => {
    const report = scanReportSchema.parse(base);
    expect(scanProblem(report, "4h", "24H", asOf)).toContain("timeframe");
    expect(scanProblem({ ...report, universe_size: 2 }, "1h", "24H", asOf)).toContain("universo");
  });

  it("rejects malformed immutable identities and decimal values", () => {
    expect(() => scanReportSchema.parse({ ...base, input_hash: "invented" })).toThrow();
    expect(() => scanReportSchema.parse({ ...base, filters: { ...base.filters, minimum_score: "NaN" } })).toThrow();
  });
});
