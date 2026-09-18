import { expect, it } from "vitest";
import { paperAccounts } from "../lib/paper";
import { upstreamURL } from "../lib/proxy";
it("allows only read-only PAPER account routes", () => {
  const path = ["paper", "accounts", "11111111-1111-4111-8111-111111111111"];
  expect(upstreamURL(path, new URLSearchParams(), "http://localhost").pathname).toBe("/api/v1/" + path.join("/"));
  for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
    expect(() => upstreamURL(path, new URLSearchParams(), "http://localhost", method)).toThrow();
  }
  expect(() => upstreamURL(["paper", "orders"], new URLSearchParams(), "http://localhost")).toThrow();
});
it("does not fabricate unavailable PAPER accounts", () => {
  expect(paperAccounts.parse([])).toEqual([]);
  expect(() => paperAccounts.parse([{ mode: "LIVE" }])).toThrow();
  expect(() => paperAccounts.parse([{ mode: "PAPER", live_ready: true }])).toThrow();
});

it("accepts exact synthetic Decimal accounting and rejects live claims", () => {
  const view = { mode: "PAPER", live_ready: false, observed_at: "2025-01-01T00:00:00Z", ready: false,
    readiness_reason: "WAITING_DATA", config: { mode: "PAPER" }, state: {
      mode: "PAPER", account_id: "11111111-1111-4111-8111-111111111111", revision: 0,
      origin: "SYNTHETIC", market_id: "synthetic:BTC", quote_currency: "USD", at: "2025-01-01T00:00:00Z",
      status: "WAITING_DATA", reason: null, last_price: null, last_close: null,
      portfolio: { cash: "10000", quantity: "0E-18", equity: "10000", reserved_cash: "0" },
      realized_pnl: "0", unrealized_pnl: null, total_fees: "0", pending: [], orders: [], fills: [],
      live_ready: false, profitability_claim: false,
    } };
  expect(paperAccounts.parse([view])[0].state.portfolio.quantity).toBe("0E-18");
  expect(() => paperAccounts.parse([{ ...view, state: { ...view.state, profitability_claim: true } }])).toThrow();
  expect(() => paperAccounts.parse([{ ...view, state: { ...view.state, portfolio: { ...view.state.portfolio, cash: "NaN" } } }])).toThrow();
});
