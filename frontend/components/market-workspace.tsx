"use client";

import dynamic from "next/dynamic";
import { AnalysisPanel } from "./analysis-panel";
import { WatchlistPanel } from "./watchlist-panel";
import { ScannerPanel } from "./scanner-panel";
import { PortfolioPanel } from "./portfolio-panel";
import { useEffect, useState } from "react";
import { z } from "zod";
import {
  assetSchema, chartProblem, marketSchema, qualityLabels, readJSON, recentRange,
  responseSchema, timeframes, validateRange, type Market, type Range, type Timeframe,
} from "@/lib/market-data";
import { zoneProblem, zoneResponseSchema, type ZoneSnapshot } from "@/lib/zones";
import type { CandleResponse } from "@/lib/market-data";
import { analysisResponseSchema } from "@/lib/analysis";

const PriceChart = dynamic(() => import("./price-chart").then(m => m.PriceChart), {
  ssr: false, loading: () => <div className="empty-chart" role="status">Preparing chart…</div>,
});
const marketsSchema = z.array(marketSchema).max(40);

function useResource<T>(url: string | null, schema: z.ZodType<T>) {
  const [result, setResult] = useState<{ url: string; data?: T; error?: string } | null>(null);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    readJSON(url, schema, controller.signal).then(data => {
      if (!controller.signal.aborted) setResult({ url, data });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setResult({
        url, error: error instanceof Error ? error.message : "Error loading data.",
      });
    });
    return () => controller.abort();
  }, [url, schema]);
  return result?.url === url ? result : null;
}

function RangeForm({ range, timeframe, onApply }: {
  range: Range; timeframe: Timeframe; onApply: (range: Range) => void;
}) {
  const [start, setStart] = useState(range.start.slice(0, 16));
  const [end, setEnd] = useState(range.end.slice(0, 16));
  const [error, setError] = useState<string | null>(null);
  return <form className="range-form" onSubmit={event => {
    event.preventDefault();
    try {
      const next = { start: new Date(start + "Z").toISOString(), end: new Date(end + "Z").toISOString() };
      const issue = validateRange(next, timeframe);
      setError(issue);
      if (!issue) onApply(next);
    } catch { setError("Enter a valid range."); }
  }}>
    <label>Start (UTC)<input type="datetime-local" required value={start} onChange={e => setStart(e.target.value)} /></label>
    <label>Fim (UTC)<input type="datetime-local" required value={end} onChange={e => setEnd(e.target.value)} /></label>
    <button className="secondary" type="submit">Apply range</button>
    {error && <p className="form-error" role="alert">{error}</p>}
  </form>;
}

export function MarketWorkspace({ initialRange }: { initialRange: Range }) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [assetType, setAssetType] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Market | null>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [range, setRange] = useState(initialRange);
  const [revision, setRevision] = useState(0);
  const [showZones, setShowZones] = useState(false);
  const catalogParams = new URLSearchParams({
    q: query, offset: String(offset), limit: "40", _refresh: String(revision),
  });
  if (assetType) catalogParams.set("asset_type", assetType);
  const catalog = useResource("/api/market-data/markets?" + catalogParams, marketsSchema);
  const metadata = useResource(selected
    ? "/api/market-data/assets/" + encodeURIComponent(selected.asset_id) : null, assetSchema);
  const candleParams = new URLSearchParams({ ...range, timeframe, limit: "1000", _refresh: String(revision) });
  const data = useResource<CandleResponse & { snapshot?: ZoneSnapshot }>(selected
    ? "/api/market-data/markets/" + encodeURIComponent(selected.market_id) + (showZones ? "/zones?" : "/candles?") + candleParams
    : null, showZones ? zoneResponseSchema : responseSchema);
  const analysisParams = new URLSearchParams({ timeframe, as_of: range.end, _refresh: String(revision) });
  const analysis = useResource(selected
    ? "/api/market-data/markets/" + encodeURIComponent(selected.market_id) + "/analysis?" + analysisParams
    : null, analysisResponseSchema);
  const response = data?.data;
  const problem = response && selected ? chartProblem(response, selected.market_id, timeframe, range)
    ?? (response.snapshot ? zoneProblem(response.snapshot, response.candles, selected.market_id, timeframe, range) : null) : null;
  const last = !problem && response?.candles.length ? response.candles[response.candles.length - 1] : null;
  const isEmpty = response?.candles.length === 0;

  return <div className="app-shell market-terminal" id="market-intelligence">
    <div className="workbench">
      <aside className="market-sidebar" aria-label="Pesquisa de markets">
        <div className="sidebar-heading"><span className="eyebrow">EXPLORAR</span><h1>Markets</h1>
          <p>Choose an asset. Observe the data.</p></div>
        <form className="search-form" onSubmit={e => { e.preventDefault(); setQuery(search); setOffset(0); setRevision(r => r + 1); }}>
          <label htmlFor="search">Search asset</label>
          <div className="search-field"><input id="search" maxLength={128} value={search}
            onChange={e => setSearch(e.target.value)} placeholder="Symbol or name…" autoComplete="off" />
            <button type="submit" aria-label="Search">↵</button></div>
        </form>
        <label className="filter-label" htmlFor="asset-type">Asset class</label>
        <select id="asset-type" value={assetType} onChange={e => { setAssetType(e.target.value); setOffset(0); }}>
          <option value="">All asset classes</option><option value="CRYPTO">Crypto</option>
          <option value="STOCK">Stocks</option><option value="ETF">ETF</option><option value="INDEX">Indices</option>
        </select>
        <div className="list-heading"><span>Market / currency</span><span>Venue</span></div>
        <div className="market-list" aria-live="polite">
          {!catalog && <p className="list-message" role="status">Loading markets…</p>}
          {catalog?.error && <div className="list-message" role="alert"><p>{catalog.error}</p>
            <button onClick={() => setRevision(r => r + 1)}>Retry</button></div>}
          {catalog?.data?.length === 0 && <div className="list-message">
            <strong>{query || assetType ? "No results" : "No markets yet"}</strong>
            <p>{query || assetType ? "Try another symbol or asset class."
              : "Markets will appear after they are registered and data is imported."}</p></div>}
          {catalog?.data?.map(market => <button key={market.market_id} className="market-item"
            aria-pressed={selected?.market_id === market.market_id} onClick={() => { setSelected(market); setRevision(r => r + 1); }}>
            <span><strong>{market.symbol}</strong><small>{market.quote_currency}</small></span>
            <span className="venue">{market.venue_id}</span>
          </button>)}
        </div>
        {(offset > 0 || catalog?.data?.length === 40) && <div className="pagination">
          <button disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 40))}>Previous</button>
          <span>Page {offset / 40 + 1}</span>
          <button disabled={catalog?.data?.length !== 40 || offset >= 100000} onClick={() => setOffset(n => n + 40)}>Next</button>
        </div>}
        <div className="sidebar-note"><span className="eyebrow">DATA BEFORE DECISIONS</span>
          <p>Zones are based on stored observations. They are not recommendations or probabilities.</p></div>
      </aside>

      <div id="workspace" className="workspace">
        <div className="workspace-heading"><div><span className="eyebrow">MARKET VIEW</span>
          <h2>{selected?.symbol ?? "The market, in detail."}</h2>
          <p>{selected ? (metadata?.data?.name ?? selected.asset_id) + " · " + selected.venue_id + " · " + selected.quote_currency
            : "Candles and volume. A direct view of the available history."}</p></div>
          <button className="secondary refresh" onClick={() => setRevision(r => r + 1)}>↻ Refresh</button></div>

        <div className="chart-panel">
          <div className="instrument-strip">
            <div><span className="eyebrow">LAST CLOSE IN RANGE</span>
              <div className="last-price">{last?.close ?? "—"} <small>{selected?.quote_currency ?? ""}</small></div>
            </div>
            <div className="period-meta"><span>Historical data</span><strong>{last
              ? new Date(last.close_time).toISOString().replace("T", " ").slice(0, 16) + " UTC"
              : "No verified price"}</strong></div>
          </div>
          <div className="chart-toolbar"><div className="timeframes" role="group" aria-label="Timeframe dos candles">
            {timeframes.map(value => <button key={value} aria-pressed={value === timeframe}
              onClick={() => { setTimeframe(value); setRange(recentRange(value, Date.parse(range.end))); setRevision(r => r + 1); }}>
              {value}</button>)}</div><span className="utc-label">UTC</span></div>
          <RangeForm key={timeframe + range.start + range.end} range={range} timeframe={timeframe}
            onApply={next => { setRange(next); setRevision(r => r + 1); }} />
          <label className="zone-toggle"><input type="checkbox" checked={showZones}
            onChange={e => { setShowZones(e.target.checked); setRevision(r => r + 1); }} />
            Show support / resistance zones</label>
          {!selected && <div className="empty-chart"><div className="empty-symbol" aria-hidden="true">⌕</div>
            <h3>Start with a market</h3><p>Search for an asset in the list and select the market you want to explore.</p>
            <span className="empty-caption">CRYPTO / STOCK / ETF / INDEX</span></div>}
          {selected && !data && <div className="empty-chart" role="status"><h3>Loading history…</h3></div>}
          {data?.error && <div className="empty-chart" role="alert"><h3>Unable to load chart</h3>
            <p>{data.error}</p><button className="secondary" onClick={() => setRevision(r => r + 1)}>Retry</button></div>}
          {selected && response && (isEmpty || problem) && <div className="empty-chart" role="status">
            <div className="quality-icon" aria-hidden="true">!</div>
            <h3>{isEmpty ? "No candles in this range" : "Chart unavailable"}</h3>
            <p>{isEmpty ? "No stored observations exist for this selection. Try another range or timeframe." : problem}</p>
            {response.quality.reason_codes.length > 0 && <ul className="quality-reasons">
              {response.quality.reason_codes.map(code => <li key={code}>{qualityLabels[code] ?? code}</li>)}</ul>}
            {response.quality.missing_intervals.length > 0 && <small>{response.quality.missing_intervals.length} intervalos em falta. Nenhum foi preenchido.</small>}
          </div>}
          {response && !problem && response.candles.length > 0 && <PriceChart key={selected?.market_id + timeframe + range.start + range.end + revision} candles={response.candles} zones={response.snapshot?.zones} />}
          <div className="data-provenance"><span>{response ? "Fonte: " + response.quality.source : "Source: awaiting selection"}</span>
            <span>{response ? response.candles.length + " observations received" : "Stored observations only"}</span></div>
        </div>
        {showZones && response?.snapshot && !problem && <section className="zone-evidence" aria-label="Zone evidence">
          <h3>Support and resistance</h3>
          <p>Explainable strength, not probability. Bands show the state at the last close and begin only when available; data received later may fall outside the chart.</p>
          {response.snapshot.zones.length === 0 ? <p role="status">No confirmed zones exist in this range.</p>
            : <div className="table-scroll" tabIndex={0}><table><caption>Confirmed zones — exact values</caption>
              <thead><tr><th>Role</th><th>Limits</th><th>Strength / 100</th><th>Evidence</th><th>Available since (UTC)</th></tr></thead>
              <tbody>{response.snapshot.zones.map(zone => <tr key={zone.zone_id}>
                <td>{zone.role === "SUPPORT" ? "Support" : "Resistance"}</td><td>{zone.lower} — {zone.upper}</td>
                <td>{zone.strength}<small> Pivots {zone.components.pivots} + contacts {zone.components.contacts} + rejections {zone.components.rejections} + recency {zone.components.recency}</small></td>
                <td>{zone.pivot_count} pivots · {zone.contacts} contacts · {zone.rejections} rejections · {zone.flips} flips</td>
                <td>{zone.visible_from}</td></tr>)}</tbody></table></div>}
          <small>Model {response.snapshot.engine_version} · Confidence is not calibrated</small>
        </section>}
        <section id="watchlists"><WatchlistPanel market={selected} timeframe={timeframe} asOf={range.end} /></section>
        <section id="scanner"><ScannerPanel timeframe={timeframe} asOf={range.end} /></section>
        <section id="portfolio"><PortfolioPanel market={selected} timeframe={timeframe} /></section>
        {selected && <section id="analysis"><AnalysisPanel result={analysis} marketId={selected.market_id}
          timeframe={timeframe} asOf={range.end} /></section>}
        {response?.quality.warnings.length ? <div className="notice" role="status">{response.quality.warnings.join(" · ")}</div> : null}
        <div className="workspace-notes"><p>Ranges are evaluated as continuous intervals. Session closes may be marked as missing intervals.</p>
          <p>The chart uses visual approximations; original values are preserved in the table.</p></div>
        {response && !problem && response.candles.length > 0 && <details className="raw-data">
          <summary>View raw values · {response.candles.length} candles</summary>
          <div className="table-scroll" tabIndex={0}><table><caption>Historical observations — UTC timestamps</caption>
            <thead><tr>{["Open UTC", "Open", "Maximum", "Low", "Close", "Volume"].map(t => <th key={t}>{t}</th>)}</tr></thead>
            <tbody>{response.candles.map(c => <tr key={c.open_time}><td>{c.open_time}</td>
              <td>{c.open}</td><td>{c.high}</td><td>{c.low}</td><td>{c.close}</td><td>{c.volume}</td></tr>)}</tbody></table></div>
        </details>}
        <footer className="workspace-footer"><span>Pocket Alpha / Market workspace</span>
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc.</a></footer>
      </div>
    </div>
  </div>;
}
