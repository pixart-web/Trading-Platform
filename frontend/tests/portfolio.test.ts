import { describe, expect, it } from "vitest";
import {
  portfolioEntrySchema, portfolioProblem, portfolioSchema, portfolioSnapshotSchema,
  snapshotProblem,
} from "../lib/portfolio";

const createdAt = "2025-01-01T00:00:00Z";
const portfolio = portfolioSchema.parse({
  schema_version: "portfolio-1.0.0", portfolio_id: "00000000-0000-0000-0000-000000000900",
  name: "Principal", base_currency: "EUR", accounting_method: "MOVING_AVERAGE_V1",
  valuation_timeframe: "1h", revision: 2, created_at: createdAt,
  updated_at: "2025-01-01T01:00:00Z",
});
const snapshot = {
  schema_version: "portfolio-snapshot-1.0.0" as const, portfolio_id: portfolio.portfolio_id,
  portfolio_revision: 2, ledger_sequence: 1, base_currency: "EUR",
  accounting_method: "MOVING_AVERAGE_V1" as const, valuation_timeframe: "1h" as const,
  as_of: "2025-01-01T02:00:00Z", generated_at: "2025-01-01T02:00:01Z",
  status: "COMPLETE" as const, cash_balance: "1000.000000000000000000",
  net_contributions: "1000.000000000000000000", total_fees: "0.000000000000000000",
  realized_pnl: "0.000000000000000000", positions: [],
  total_cost_basis: "0.000000000000000000", total_market_value: "0.000000000000000000",
  unrealized_pnl: "0.000000000000000000", equity: "1000.000000000000000000",
  input_hash: "a".repeat(64),
};

describe("portfolio contracts", () => {
  it("accepts exact empty valuation and coherent metadata", () => {
    const value = portfolioSnapshotSchema.parse(snapshot);
    expect(portfolioProblem(portfolio)).toBeNull();
    expect(snapshotProblem(value, portfolio)).toBeNull();
  });

  it("keeps missing prices explicit and blocks invented totals", () => {
    const position = { market: { market_id: "test-market", asset_id: "test-asset", symbol: "TEST",
      name: "Test", asset_type: "STOCK", venue_id: "test-venue", quote_currency: "EUR" },
      status: "OPEN", quantity: "1", average_cost: "100", cost_basis: "100",
      realized_pnl: "0", last_price: null, price_time: null, price_available_at: null,
      market_value: null, unrealized_pnl: null };
    const partial = portfolioSnapshotSchema.parse({ ...snapshot, status: "PARTIAL",
      positions: [position], total_cost_basis: "100", total_market_value: null,
      unrealized_pnl: null, equity: null });
    expect(snapshotProblem(partial, portfolio)).toBeNull();
    expect(snapshotProblem({ ...partial, status: "COMPLETE" }, portfolio)).toContain("cobertura");
  });

  it("validates immutable ledger identities and decimal strings", () => {
    const entry = portfolioEntrySchema.parse({
      schema_version: "portfolio-entry-1.0.0", entry_id: "00000000-0000-0000-0000-000000000901",
      portfolio_id: portfolio.portfolio_id, sequence: 1, entry_type: "DEPOSIT", currency: "EUR",
      cash_amount: "1000.000000000000000000", market_id: null, asset_id: null,
      quantity: null, unit_price: null, fee: "0.000000000000000000",
      gross_value: "1000.000000000000000000", cash_effect: "1000.000000000000000000",
      occurred_at: createdAt, recorded_at: createdAt, note: null,
    });
    expect(entry.sequence).toBe(1);
    expect(() => portfolioEntrySchema.parse({ ...entry, cash_effect: "NaN" })).toThrow();
  });
});
