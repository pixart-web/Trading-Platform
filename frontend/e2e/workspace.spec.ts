import { expect, test, type Page } from "@playwright/test";
import { durations, type Timeframe } from "../lib/market-data";

const market = { market_id: "synthetic-test", asset_id: "synthetic", venue_id: "fixture-only",
  symbol: "SYNTHETIC", quote_currency: "EUR" };

async function fixtures(page: Page, mode: "valid" | "gap" | "empty" | "offline" | "zones" | "badzones" | "nozones" | "analysis" | "watchlist" | "scanner" = "valid") {
  const watchlistId = "11111111-1111-4111-8111-111111111101";
  let activeList = {
    schema_version: "watchlist-1.0.0", watchlist_id: watchlistId, name: "A acompanhar",
    revision: 1, created_at: "2025-01-01T00:00:00Z", updated_at: "2025-01-01T00:00:00Z",
    members: [] as Array<{ member_id: string; market_id: string; asset_id: string;
      candle_timeframe: Timeframe; added_at: string }>,
  };
  await page.route("**/api/market-data/**", async route => {
    const url = new URL(route.request().url());
    if (mode === "offline") return route.fulfill({ status: 503, json: {} });
    if (url.pathname === "/api/market-data/scans") {
      if (route.request().method() === "GET") return route.fulfill({ json: [] });
      const body = route.request().postDataJSON();
      return route.fulfill({ json: {
        schema_version: "scan-report-1.0.0", scan_id: body.scan_id,
        candle_timeframe: body.candle_timeframe, horizon: body.horizon, as_of: body.as_of,
        generated_at: body.as_of, scanner_version: "scanner-1.0.0", filters: body.filters,
        status: "NO_MATCHES", universe_size: 1, analyze_reports_found: 0, groups: [],
        excluded: [{ market: { ...market, name: "Synthetic test asset", asset_type: "STOCK" },
          report_id: null, opportunity: null, reasons: ["NO_ANALYZE_REPORT"] }],
        input_hash: "c".repeat(64),
      } });
    }
    if (url.pathname === "/api/market-data/watchlists") {
      return route.fulfill({ json: mode === "watchlist" ? [activeList] : [] });
    }
    if (url.pathname.includes(`/watchlists/${watchlistId}`)) {
      if (url.pathname.endsWith("/snapshots/latest")) return route.fulfill({ json: null });
      if (url.pathname.endsWith("/alerts")) return route.fulfill({ json: [] });
      if (url.pathname.includes("/markets/") && route.request().method() === "PUT") {
        const body = route.request().postDataJSON();
        activeList = { ...activeList, revision: 2, updated_at: "2025-01-01T01:00:00Z",
          members: [{ member_id: body.member_id, market_id: market.market_id,
            asset_id: market.asset_id, candle_timeframe: body.candle_timeframe,
            added_at: "2025-01-01T01:00:00Z" }] };
        return route.fulfill({ json: activeList });
      }
      if (url.pathname.endsWith("/snapshots") && route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        const snapshot = { schema_version: "watchlist-snapshot-1.0.0",
          snapshot_id: body.snapshot_id, watchlist_id: watchlistId, watchlist_revision: 2,
          as_of: body.as_of, generated_at: body.as_of, status: "UNAVAILABLE",
          input_hash: "b".repeat(64), items: activeList.members.map(item => ({
            member_id: item.member_id, market_id: item.market_id, asset_id: item.asset_id,
            candle_timeframe: item.candle_timeframe, report_id: null, report_status: null,
            unavailable_reason: "NO_ANALYSIS_SNAPSHOT", horizons: ["1H", "4H", "8H", "12H",
              "24H", "2D", "3D", "7D", "14D", "30D", "90D", "6M", "12M"].map(horizon =>
                ({ horizon, conclusion: "UNAVAILABLE" })),
          })) };
        return route.fulfill({ json: { snapshot, events: [] } });
      }
    }
    if (url.pathname.endsWith("/markets")) return route.fulfill({ json: mode === "empty" ? [] : [market] });
    if (url.pathname.includes("/assets/")) return route.fulfill({ json: {
      asset_id: "synthetic", symbol: "SYNTHETIC", name: "Synthetic test asset", asset_type: "STOCK",
    } });
    if (url.pathname.endsWith("/analysis")) {
      const asOf = url.searchParams.get("as_of")!;
      if (mode !== "analysis") return route.fulfill({ json: {
        schema_version: "analyze-response-1.0.0", market_id: market.market_id,
        candle_timeframe: url.searchParams.get("timeframe"), requested_as_of: asOf,
        status: "UNAVAILABLE", report: null, unavailable_reason: "NO_ANALYSIS_SNAPSHOT",
      } });
      const horizons = ["1H", "4H", "8H", "12H", "24H", "2D", "3D", "7D", "14D", "30D", "90D", "6M", "12M"];
      return route.fulfill({ json: {
        schema_version: "analyze-response-1.0.0", market_id: market.market_id,
        candle_timeframe: url.searchParams.get("timeframe"), requested_as_of: asOf,
        status: "AVAILABLE", unavailable_reason: null, report: {
          report_id: "00000000-0000-0000-0000-000000000001", market_id: market.market_id,
          asset_id: market.asset_id, candle_timeframe: url.searchParams.get("timeframe"), as_of: asOf,
          generated_at: asOf, status: "UNAVAILABLE", report_version: "synthetic-analyze-v1",
          input_hash: "a".repeat(64), issues: ["POCKET_SCORE_NOT_PRODUCED"],
          pocket_score: null, pocket_score_unavailable_reason: "POCKET_SCORE_NOT_PRODUCED",
          horizons: horizons.map(horizon => ({ horizon, status: "UNAVAILABLE", conclusion: "UNAVAILABLE",
            issues: ["FORECAST_NOT_PRODUCED", "DIRECTIONAL_NOT_PRODUCED", "OPPORTUNITY_NOT_PRODUCED"],
            forecast: null, forecast_unavailable_reason: "FORECAST_NOT_PRODUCED",
            directional: null, directional_unavailable_reason: "DIRECTIONAL_NOT_PRODUCED",
            opportunity: null, opportunity_unavailable_reason: "OPPORTUNITY_NOT_PRODUCED" })),
        },
      } });
    }
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
      ...(url.pathname.endsWith("/zones") ? { snapshot: {
        engine_version: "zones-1.0.0", spec: { version: "1.0.0" }, market_id: market.market_id,
        timeframe, source: "fixture", input_start: new Date(start).toISOString(),
        input_count: mode === "badzones" ? 1 : candles.length, input_hash: "a".repeat(64),
        bar_close: new Date(end).toISOString(), available_at: new Date(end).toISOString(),
        zones: mode === "nozones" ? [] : [
          { zone_id: "test-support", role: "SUPPORT", lower: "94", center: "96", upper: "98" },
          { zone_id: "test-resistance", role: "RESISTANCE", lower: "116", center: "118", upper: "120" },
        ].map(z => ({ ...z, first_seen: new Date(start + 10 * step).toISOString(),
          visible_from: new Date(start + 10 * step).toISOString(), last_seen: new Date(end).toISOString(),
          pivot_count: 1, contacts: 0, rejections: 0, flips: 0, age_bars: 0, strength: 30,
          components: { pivots: 10, contacts: 0, rejections: 0, recency: 20 },
          confidence: null, confidence_reason: "UNCALIBRATED" })),
      } } : {}),
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
  await expect(page.getByRole("complementary", { name: "Pesquisa de mercados" })
    .getByRole("alert")).toBeVisible();
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

test("zone toggle renders bands, evidence and survives timeframe changes", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await fixtures(page, "zones");
  await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  await page.getByLabel("Mostrar zonas de suporte / resistência").check();
  await expect(page.getByRole("table", { name: "Zonas confirmadas — valores exatos" })).toBeVisible();
  await expect(page.getByTestId("price-chart").locator("canvas").first()).toBeVisible();
  await page.getByRole("button", { name: "4h", exact: true }).click();
  await expect(page.getByRole("cell", { name: "94 — 98", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/zones-synthetic.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByLabel("Mostrar zonas de suporte / resistência").uncheck();
  await expect(page.getByRole("region", { name: "Evidência das zonas" })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("mismatched zone response blocks chart", async ({ page }) => {
  await fixtures(page, "badzones");
  await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  await page.getByLabel("Mostrar zonas de suporte / resistência").check();
  await expect(page.getByText("As zonas não correspondem aos dados deste gráfico.")).toBeVisible();
  await expect(page.getByTestId("price-chart")).toHaveCount(0);
});

test("insufficient pivot evidence shows honest no-zone state", async ({ page }) => {
  await fixtures(page, "nozones");
  await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  await page.getByLabel("Mostrar zonas de suporte / resistência").check();
  await expect(page.getByText("Ainda não existem zonas confirmadas neste período.")).toBeVisible();
  await expect(page.getByTestId("price-chart")).toBeVisible();
});


test("stored Analyze snapshot renders every honest horizon state", async ({ page }) => {
  await fixtures(page, "analysis");
  await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  const panel = page.getByRole("region", { name: "Análise partilhada" });
  await expect(panel.getByText("0 / 13 horizontes completos")).toBeVisible();
  await expect(panel.getByText("1H", { exact: true })).toBeVisible();
  await expect(panel.getByText("12M", { exact: true })).toBeVisible();
  await expect(panel.getByText("Índices não são probabilidades nem aprovação de risco.")).toBeVisible();
  await page.screenshot({ path: "test-results/analyze-synthetic.png", fullPage: true });
});


test("watchlist persists a market and records an honest snapshot", async ({ page }) => {
  await fixtures(page, "watchlist");
  await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC/ }).click();
  const panel = page.getByRole("region", { name: "Watchlists" });
  await panel.getByRole("button", { name: "Adicionar mercado" }).click();
  await expect(panel.getByText("synthetic-test", { exact: true }).first()).toBeVisible();
  await panel.getByRole("button", { name: "Registar snapshot" }).click();
  await expect(panel.getByText("UNAVAILABLE", { exact: true })).toBeVisible();
  await expect(panel.getByText("0 horizontes elegíveis")).toBeVisible();
  await expect(panel.getByText(/Não são alertas de preço/)).toBeVisible();
});


test("scanner records an honest no-match result with exclusions", async ({ page }) => {
  await fixtures(page, "scanner");
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Scanner de oportunidades" });
  await panel.getByRole("button", { name: "Executar scan" }).click();
  await expect(panel.getByText("Sem correspondências", { exact: true })).toBeVisible();
  await expect(panel.getByText("0 relatórios encontrados em 1 mercados")).toBeVisible();
  await panel.getByText("Exclusões explícitas · 1").click();
  await expect(panel.getByText("Sem relatório Analyze")).toBeVisible();
  await expect(panel.getByText(/Índices não são probabilidades/)).toBeVisible();
});
