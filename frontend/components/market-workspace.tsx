"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { z } from "zod";
import {
  assetSchema, chartProblem, marketSchema, qualityLabels, readJSON, recentRange,
  responseSchema, timeframes, validateRange, type Market, type Range, type Timeframe,
} from "@/lib/market-data";

const PriceChart = dynamic(() => import("./price-chart").then(m => m.PriceChart), {
  ssr: false, loading: () => <div className="empty-chart" role="status">A preparar o gráfico…</div>,
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
        url, error: error instanceof Error ? error.message : "Erro ao consultar os dados.",
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
    } catch { setError("Introduz um período válido."); }
  }}>
    <label>Início (UTC)<input type="datetime-local" required value={start} onChange={e => setStart(e.target.value)} /></label>
    <label>Fim (UTC)<input type="datetime-local" required value={end} onChange={e => setEnd(e.target.value)} /></label>
    <button className="secondary" type="submit">Aplicar período</button>
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
  const catalogParams = new URLSearchParams({
    q: query, offset: String(offset), limit: "40", _refresh: String(revision),
  });
  if (assetType) catalogParams.set("asset_type", assetType);
  const catalog = useResource("/api/market-data/markets?" + catalogParams, marketsSchema);
  const metadata = useResource(selected
    ? "/api/market-data/assets/" + encodeURIComponent(selected.asset_id) : null, assetSchema);
  const candleParams = new URLSearchParams({ ...range, timeframe, limit: "1000", _refresh: String(revision) });
  const data = useResource(selected
    ? "/api/market-data/markets/" + encodeURIComponent(selected.market_id) + "/candles?" + candleParams
    : null, responseSchema);
  const response = data?.data;
  const problem = response && selected ? chartProblem(response, selected.market_id, timeframe, range) : null;
  const last = !problem && response?.candles.length ? response.candles[response.candles.length - 1] : null;
  const isEmpty = response?.candles.length === 0;

  return <div className="app-shell">
    <a className="skip-link" href="#workspace">Ir para o gráfico</a>
    <header className="app-header">
      <Link className="brand" href="/" aria-label="Pocket Alpha — início"><span className="brand-mark">pα</span>Pocket Alpha</Link>
      <span className="header-section">Mercados <span>/</span> Gráficos</span>
      <span className="mode-label">Consulta histórica</span>
    </header>
    <div className="workbench">
      <aside className="market-sidebar" aria-label="Pesquisa de mercados">
        <div className="sidebar-heading"><span className="eyebrow">EXPLORAR</span><h1>Mercados</h1>
          <p>Escolhe o ativo. Observa os dados.</p></div>
        <form className="search-form" onSubmit={e => { e.preventDefault(); setQuery(search); setOffset(0); setRevision(r => r + 1); }}>
          <label htmlFor="search">Pesquisar ativo</label>
          <div className="search-field"><input id="search" maxLength={128} value={search}
            onChange={e => setSearch(e.target.value)} placeholder="Símbolo ou nome…" autoComplete="off" />
            <button type="submit" aria-label="Pesquisar">↵</button></div>
        </form>
        <label className="filter-label" htmlFor="asset-type">Classe de ativo</label>
        <select id="asset-type" value={assetType} onChange={e => { setAssetType(e.target.value); setOffset(0); }}>
          <option value="">Todas as classes</option><option value="CRYPTO">Cripto</option>
          <option value="STOCK">Ações</option><option value="ETF">ETF</option><option value="INDEX">Índices</option>
        </select>
        <div className="list-heading"><span>Mercado / moeda</span><span>Venue</span></div>
        <div className="market-list" aria-live="polite">
          {!catalog && <p className="list-message" role="status">A consultar mercados…</p>}
          {catalog?.error && <div className="list-message" role="alert"><p>{catalog.error}</p>
            <button onClick={() => setRevision(r => r + 1)}>Tentar novamente</button></div>}
          {catalog?.data?.length === 0 && <div className="list-message">
            <strong>{query || assetType ? "Sem resultados" : "Ainda não existem mercados"}</strong>
            <p>{query || assetType ? "Experimenta outro símbolo ou classe de ativo."
              : "Os mercados aparecerão depois de serem registados e os dados importados."}</p></div>}
          {catalog?.data?.map(market => <button key={market.market_id} className="market-item"
            aria-pressed={selected?.market_id === market.market_id} onClick={() => { setSelected(market); setRevision(r => r + 1); }}>
            <span><strong>{market.symbol}</strong><small>{market.quote_currency}</small></span>
            <span className="venue">{market.venue_id}</span>
          </button>)}
        </div>
        {(offset > 0 || catalog?.data?.length === 40) && <div className="pagination">
          <button disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 40))}>Anterior</button>
          <span>Página {offset / 40 + 1}</span>
          <button disabled={catalog?.data?.length !== 40 || offset >= 100000} onClick={() => setOffset(n => n + 40)}>Seguinte</button>
        </div>}
        <div className="sidebar-note"><span className="eyebrow">DADOS, ANTES DE DECISÕES</span>
          <p>Sem indicadores ou recomendações nesta fase. Cada gráfico depende de observações armazenadas.</p></div>
      </aside>

      <main id="workspace" className="workspace">
        <div className="workspace-heading"><div><span className="eyebrow">VISÃO DE MERCADO</span>
          <h2>{selected?.symbol ?? "O mercado, em detalhe."}</h2>
          <p>{selected ? (metadata?.data?.name ?? selected.asset_id) + " · " + selected.venue_id + " · " + selected.quote_currency
            : "Candles e volume. Uma leitura direta do histórico disponível."}</p></div>
          <button className="secondary refresh" onClick={() => setRevision(r => r + 1)}>↻ Atualizar</button></div>

        <div className="chart-panel">
          <div className="instrument-strip">
            <div><span className="eyebrow">ÚLTIMO FECHO NO PERÍODO</span>
              <div className="last-price">{last?.close ?? "—"} <small>{selected?.quote_currency ?? ""}</small></div>
            </div>
            <div className="period-meta"><span>Dados históricos</span><strong>{last
              ? new Date(last.close_time).toISOString().replace("T", " ").slice(0, 16) + " UTC"
              : "Sem preço verificado"}</strong></div>
          </div>
          <div className="chart-toolbar"><div className="timeframes" role="group" aria-label="Timeframe dos candles">
            {timeframes.map(value => <button key={value} aria-pressed={value === timeframe}
              onClick={() => { setTimeframe(value); setRange(recentRange(value, Date.parse(range.end))); setRevision(r => r + 1); }}>
              {value}</button>)}</div><span className="utc-label">UTC</span></div>
          <RangeForm key={timeframe + range.start + range.end} range={range} timeframe={timeframe}
            onApply={next => { setRange(next); setRevision(r => r + 1); }} />
          {!selected && <div className="empty-chart"><div className="empty-symbol" aria-hidden="true">⌕</div>
            <h3>Começa por um mercado</h3><p>Pesquisa um ativo na lista e seleciona o mercado que queres explorar.</p>
            <span className="empty-caption">CRYPTO / STOCK / ETF / INDEX</span></div>}
          {selected && !data && <div className="empty-chart" role="status"><h3>A consultar o histórico…</h3></div>}
          {data?.error && <div className="empty-chart" role="alert"><h3>Não foi possível carregar o gráfico</h3>
            <p>{data.error}</p><button className="secondary" onClick={() => setRevision(r => r + 1)}>Tentar novamente</button></div>}
          {selected && response && (isEmpty || problem) && <div className="empty-chart" role="status">
            <div className="quality-icon" aria-hidden="true">!</div>
            <h3>{isEmpty ? "Sem candles neste período" : "Gráfico indisponível"}</h3>
            <p>{isEmpty ? "Não há observações armazenadas para esta seleção. Experimenta outro período ou timeframe." : problem}</p>
            {response.quality.reason_codes.length > 0 && <ul className="quality-reasons">
              {response.quality.reason_codes.map(code => <li key={code}>{qualityLabels[code] ?? code}</li>)}</ul>}
            {response.quality.missing_intervals.length > 0 && <small>{response.quality.missing_intervals.length} intervalos em falta. Nenhum foi preenchido.</small>}
          </div>}
          {response && !problem && response.candles.length > 0 && <PriceChart key={selected?.market_id + timeframe + range.start + range.end + revision} candles={response.candles} />}
          <div className="data-provenance"><span>{response ? "Fonte: " + response.quality.source : "Fonte: aguardando seleção"}</span>
            <span>{response ? response.candles.length + " observações recebidas" : "Apenas observações armazenadas"}</span></div>
        </div>
        {response?.quality.warnings.length ? <div className="notice" role="status">{response.quality.warnings.join(" · ")}</div> : null}
        <div className="workspace-notes"><p>Os períodos são avaliados como intervalos contínuos. Fechos de sessão podem ser assinalados como intervalos em falta.</p>
          <p>O gráfico usa aproximações visuais; os valores originais são preservados na tabela.</p></div>
        {response && !problem && response.candles.length > 0 && <details className="raw-data">
          <summary>Consultar valores originais · {response.candles.length} candles</summary>
          <div className="table-scroll" tabIndex={0}><table><caption>Observações históricas — timestamps UTC</caption>
            <thead><tr>{["Abertura UTC", "Abertura", "Máximo", "Mínimo", "Fecho", "Volume"].map(t => <th key={t}>{t}</th>)}</tr></thead>
            <tbody>{response.candles.map(c => <tr key={c.open_time}><td>{c.open_time}</td>
              <td>{c.open}</td><td>{c.high}</td><td>{c.low}</td><td>{c.close}</td><td>{c.volume}</td></tr>)}</tbody></table></div>
        </details>}
        <footer className="workspace-footer"><span>Pocket Alpha / Market workspace</span>
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc.</a></footer>
      </main>
    </div>
  </div>;
}
