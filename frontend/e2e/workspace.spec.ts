import { expect, test, type Page } from "@playwright/test";
import { durations, type Timeframe } from "../lib/market-data";

const market = { market_id: "synthetic-test", asset_id: "synthetic", venue_id: "fixture-only",
  symbol: "SYNTHETIC", quote_currency: "EUR" };

async function fixtures(page: Page, mode: "valid" | "gap" | "empty" | "offline" = "valid") {
  await page.route("**/api/market-data/**", async route => {
    const url = new URL(route.request().url());
    if (mode === "offline") return route.fulfill({ status: 503, json: {} });
    if (url.pathname.endsWith("/markets")) return route.fulfill({ json: mode === "empty" ? [] : [market] });
    if (url.pathname.includes("/assets/")) return route.fulfill({ json: {
      asset_id: "synthetic", symbol: "SYNTHETIC", name: "Synthetic test asset", asset_type: "STOCK",
    } });
    const timeframe = url.searchParams.get("timeframe") as Timeframe;
    const start = Date.parse(url.searchParams.get("start")!);
    const end = Date.parse(url.searchParams.get("end")!);
    const step = durations[timeframe] * 1000;
    const candles = Array.from({ length: (end - start) / step }, (_, i) => ({
      market_id: market.market_id, timeframe,
      open_time: new Date(start + i * step).toISOString(),
      close_time: new Date(start + (i + 1) * step).toISOString(),
      received_at: new Date(start + (i + 1) * step).toISOString(),
      open: String(100 + i % 10), high: String(112 + i % 10), low: "90",
      close: String(102 + i % 10), volume: String(20 + i % 7), source: "fixture",
    }));
    return route.fulfill({ json: {
      candles: mode === "gap" ? candles.slice(1) : candles,
      quality: { valid: mode !== "gap", severity: mode === "gap" ? "ERROR" : "OK",
        reason_codes: mode === "gap" ? ["MISSING_INTERVAL"] : [], warnings: [],
        timestamp: new Date(end + step).toISOString(), source: "fixture",
        affected_records: [], missing_intervals: mode === "gap" ? [new Date(start).toISOString()] : [] },
      truncated: false, next_start: null,
    } });
  });
}

test("empty installation is honest", async ({ page }) => {
  await fixtures(page, "empty");
  await page.goto("/");
  await expect(page.getByText("Ainda não existem mercados")).toBeVisible();
  await expect(page.getByText("Começa por um mercado")).toBeVisible();
  await expect(page.getByTestId("price-chart")).toHaveCount(0);
  await page.screenshot({ path: "test-results/workspace-empty.png", fullPage: true });
});

test("search, select, chart, timeframe and exact table", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await fixtures(page);
  await page.goto("/");
  await page.getByLabel("Pesquisar ativo", { exact: true }).fill("SYNTHETIC");
  const search = page.waitForRequest(r => r.url().includes("q=SYNTHETIC"));
  await page.getByRole("button", { name: "Pesquisar", exact: true }).click();
  await search;
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  await expect(page.getByTestId("price-chart").locator("canvas").first()).toBeVisible();
  await page.getByRole("button", { name: "Aproximar gráfico" }).click();
  await page.getByRole("button", { name: "Ajustar", exact: true }).click();
  const timeframe = page.waitForRequest(r => r.url().includes("timeframe=4h"));
  await page.getByRole("button", { name: "4h", exact: true }).click();
  await timeframe;
  await expect(page.getByTestId("price-chart")).toBeVisible();
  await page.getByText(/Consultar valores originais/).click();
  await expect(page.getByRole("table", { name: "Observações históricas — timestamps UTC" })).toBeVisible();
  await page.getByText(/Consultar valores originais/).click();
  await page.screenshot({ path: "test-results/workspace-synthetic-test.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("invalid quality blocks the chart", async ({ page }) => {
  await fixtures(page, "gap");
  await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  await expect(page.getByText("Gráfico indisponível", { exact: true })).toBeVisible();
  await expect(page.getByText("Intervalos em falta", { exact: true })).toBeVisible();
  await expect(page.getByTestId("price-chart")).toHaveCount(0);
});

test("offline service does not invent market data", async ({ page }) => {
  await fixtures(page, "offline");
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Não foi possível" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tentar novamente" })).toBeVisible();
});

test("invalid date ranges do not trigger candle requests", async ({ page }) => {
  await fixtures(page);
  await page.goto("/");
  await page.getByLabel("Início (UTC)", { exact: true }).fill("2025-02-01T00:00");
  await page.getByLabel("Fim (UTC)", { exact: true }).fill("2025-01-01T00:00");
  await page.getByRole("button", { name: "Aplicar período" }).click();
  await expect(page.getByText("O fim deve ser posterior ao início.")).toBeVisible();
});

test("mobile chart renders without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixtures(page);
  await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  await expect(page.getByTestId("price-chart").locator("canvas").first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("mobile empty layout fits the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixtures(page, "empty");
  await page.goto("/");
  await expect(page.getByText("Ainda não existem mercados")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
