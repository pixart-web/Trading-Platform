import { describe, expect, it } from "vitest";
import {
  intelligenceProblem, portfolioIntelligenceSchema,
} from "../lib/portfolio-intelligence";

const portfolio = {
  schema_version: "portfolio-1.0.0" as const,
  portfolio_id: "00000000-0000-0000-0000-000000001700",
  name: "Principal", base_currency: "EUR", accounting_method: "MOVING_AVERAGE_V1" as const,
  valuation_timeframe: "1h" as const, revision: 4,
  created_at: "2025-01-01T00:00:00Z", updated_at: "2025-01-01T01:00:00Z",
};
const unavailable = (reason: string) => ({
  status: "UNAVAILABLE", value: null, reason, explanation: "Explicitly unavailable.",
});
const report = {
  schema_version: "portfolio-intelligence-report-1.0.0",
  analysis_id: "00000000-0000-0000-0000-000000001701",
  portfolio_id: portfolio.portfolio_id, portfolio_revision: 4, ledger_sequence: 3,
  timeframe: "1h", benchmark_market_id: null,
  as_of: "2025-01-02T00:00:00Z", generated_at: "2025-01-02T00:00:01Z",
  status: "PARTIAL",
  policy: { schema_version: "portfolio-intelligence-policy-1.0.0",
    policy_version: "portfolio-intelligence-1.0.0", lookback_bars: 60,
    minimum_observations: 20, maximum_price_age_bars: 3 },
  policy_hash: "a".repeat(64), portfolio_input_hash: "b".repeat(64), equity: "1000",
  allocations: [{ dimension: "MARKET", key: "test-market", value: "500",
    portfolio_weight: "0.5" }],
  concentrations: [], market_risk: [], correlations: [],
  portfolio_per_bar_volatility: unavailable("INSUFFICIENT_HISTORY"),
  portfolio_beta: unavailable("BENCHMARK_NOT_CONFIGURED"), risk_contributions: [],
  sector_concentration: unavailable("SECTOR_DATA_UNAVAILABLE"),
  drawdown: unavailable("NAV_HISTORY_UNAVAILABLE"),
  liquidity: unavailable("LIQUIDITY_DATA_UNAVAILABLE"),
  regime_exposure: unavailable("REGIME_ATTRIBUTION_UNAVAILABLE"),
  horizon_exposure: unavailable("HORIZON_ATTRIBUTION_UNAVAILABLE"),
  observations: [{ code: "ACCOUNTING_CONTEXT", severity: "INFO",
    message: "Accounting context only.", evidence: ["realized_pnl=0"] }],
  input_hash: "c".repeat(64),
};

describe("portfolio intelligence contracts", () => {
  it("accepts an identity-matched report with explicit unavailable metrics", () => {
    const value = portfolioIntelligenceSchema.parse(report);
    expect(intelligenceProblem(value, portfolio)).toBeNull();
    expect(value.drawdown.value).toBeNull();
  });

  it("rejects incoherent metric state and noncanonical allocations", () => {
    expect(() => portfolioIntelligenceSchema.parse({
      ...report, drawdown: { ...unavailable("NAV_HISTORY_UNAVAILABLE"), value: "0.1" },
    })).toThrow();
    const value = portfolioIntelligenceSchema.parse({
      ...report,
      allocations: [
        { dimension: "MARKET", key: "z", value: "1", portfolio_weight: "0.5" },
        { dimension: "MARKET", key: "a", value: "1", portfolio_weight: "0.5" },
      ],
    });
    expect(intelligenceProblem(value, portfolio)).toContain("canónica");
  });

  it("rejects reports from a future portfolio revision", () => {
    const value = portfolioIntelligenceSchema.parse({ ...report, portfolio_revision: 5 });
    expect(intelligenceProblem(value, portfolio)).toContain("versão");
  });
});
