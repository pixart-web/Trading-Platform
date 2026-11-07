import { expect, test } from "./authenticated";
test("PAPER is unmistakable and empty balances are not fabricated", async ({ page }) => {
  await page.route("**/api/market-data/paper/accounts", route => route.fulfill({ json: [] }));
  await page.goto("/paper");
  await expect(page.getByRole("heading", { name: "PAPER — simulated execution", exact: true })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("No orders are sent to a real broker");
  await expect(page.getByText("No PAPER account is registered.", { exact: false })).toBeVisible();
  await expect(page.getByText("Simulated cash", { exact: false })).toHaveCount(0);
  await page.screenshot({ path: "test-results/paper-empty.png", fullPage: true });
});
test("invalid or unreachable PAPER storage stays unavailable", async ({ page }) => {
  await page.route("**/api/market-data/paper/accounts", route => route.fulfill({ status: 503, json: {} }));
  await page.goto("/paper");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("PAPER unavailable");
});

test("synthetic PAPER accounting stays labelled and suspension is visible", async ({ page }) => {
  const at = "2025-01-01T00:00:00Z";
  const view = { mode: "PAPER", live_ready: false, observed_at: at, ready: false,
    readiness_reason: "FEED_DISCONNECTED", config: { mode: "PAPER" }, state: {
      mode: "PAPER", account_id: "11111111-1111-4111-8111-111111111111", revision: 1,
      origin: "SYNTHETIC", market_id: "synthetic:BTC", quote_currency: "USD", at,
      status: "SUSPENDED", reason: "FEED_DISCONNECTED", last_price: null, last_close: null,
      portfolio: { cash: "10000", quantity: "0E-18", equity: "10000", reserved_cash: "0" },
      realized_pnl: "0", unrealized_pnl: null, total_fees: "0", pending: [], orders: [], fills: [],
      live_ready: false, profitability_claim: false,
    } };
  await page.route("**/api/market-data/paper/accounts", route => route.fulfill({ json: [view] }));
  await page.goto("/paper");
  await expect(page.getByText("Synthetic data · simulated execution", { exact: true })).toBeVisible();
  await expect(page.getByText("State at observation:", { exact: false })).toContainText("SUSPENDED");
  await expect(page.getByText("State at observation:", { exact: false })).toContainText("FEED_DISCONNECTED");
  await expect(page.locator("dl")).toContainText("Simulated cash (USD)10000");
  await expect(page.getByRole("button", { name: /LIVE|enviar ordem/i })).toHaveCount(0);
  await page.screenshot({ path: "test-results/paper-synthetic.png", fullPage: true });
});
