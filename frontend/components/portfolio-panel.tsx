"use client";

import { useEffect, useState } from "react";
import { z } from "zod";
import type { Market, Timeframe } from "@/lib/market-data";
import { PortfolioIntelligencePanel } from "@/components/portfolio-intelligence-panel";
import {
  portfolioEntriesSchema, portfolioEntryResultSchema, portfolioProblem, portfolioSchema,
  portfoliosSchema, portfolioSnapshotSchema, snapshotProblem, type EntryType,
  type Portfolio, type PortfolioEntry, type PortfolioSnapshot,
} from "@/lib/portfolio";

type State = { portfolios: Portfolio[]; selectedId: string | null; snapshot: PortfolioSnapshot | null;
  entries: PortfolioEntry[]; loading: boolean; busy: boolean; error: string | null };

async function request<T>(url: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store", headers: {
    "Content-Type": "application/json", ...(init?.headers ?? {}),
  } });
  if (!response.ok) {
    let detail = "Não foi possível atualizar a carteira.";
    try { const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail; } catch { /* use safe fallback */ }
    throw new Error(response.status === 409 ? "A carteira mudou noutro pedido. Atualiza e repete a operação." : detail);
  }
  return schema.parse(await response.json());
}

function nowInput(): string { return new Date().toISOString().slice(0, 16); }

export function PortfolioPanel({ market, timeframe }: { market: Market | null; timeframe: Timeframe }) {
  const [state, setState] = useState<State>({ portfolios: [], selectedId: null, snapshot: null,
    entries: [], loading: true, busy: false, error: null });
  const [name, setName] = useState("Carteira principal");
  const [currency, setCurrency] = useState("EUR");
  const [entryType, setEntryType] = useState<EntryType>("DEPOSIT");
  const [cashAmount, setCashAmount] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [fee, setFee] = useState("0");
  const [occurredAt, setOccurredAt] = useState(nowInput);
  const selected = state.portfolios.find(item => item.portfolio_id === state.selectedId) ?? null;

  async function loadDashboard(portfolio: Portfolio, portfolios = state.portfolios) {
    const asOf = new Date().toISOString();
    const [snapshot, entries] = await Promise.all([
      request(`/api/market-data/portfolios/${portfolio.portfolio_id}/snapshot?as_of=${encodeURIComponent(asOf)}`, portfolioSnapshotSchema),
      request(`/api/market-data/portfolios/${portfolio.portfolio_id}/entries?limit=100`, portfolioEntriesSchema),
    ]);
    const problem = snapshotProblem(snapshot, portfolio);
    setState(old => ({ ...old, portfolios, selectedId: portfolio.portfolio_id,
      snapshot: problem ? null : snapshot, entries, loading: false, error: problem }));
  }

  useEffect(() => {
    const controller = new AbortController();
    request("/api/market-data/portfolios", portfoliosSchema, { signal: controller.signal })
      .then(portfolios => {
        if (controller.signal.aborted) return;
        const first = portfolios[0] ?? null;
        setState(old => ({ ...old, portfolios, selectedId: first?.portfolio_id ?? null, loading: false }));
        if (first) {
          const asOf = new Date().toISOString();
          Promise.all([
            request(`/api/market-data/portfolios/${first.portfolio_id}/snapshot?as_of=${encodeURIComponent(asOf)}`,
              portfolioSnapshotSchema, { signal: controller.signal }),
            request(`/api/market-data/portfolios/${first.portfolio_id}/entries?limit=100`,
              portfolioEntriesSchema, { signal: controller.signal }),
          ]).then(([snapshot, entries]) => {
            if (controller.signal.aborted) return;
            const problem = snapshotProblem(snapshot, first);
            setState(old => ({ ...old, snapshot: problem ? null : snapshot, entries,
              error: problem, loading: false }));
          }).catch(error => {
            if (!controller.signal.aborted) setState(old => ({ ...old, loading: false,
              error: error instanceof Error ? error.message : "Carteira indisponível." }));
          });
        }
      }).catch(error => { if (!controller.signal.aborted) setState(old => ({ ...old, loading: false,
        error: error instanceof Error ? error.message : "Carteiras indisponíveis." })); });
    return () => controller.abort();
  }, []);

  async function mutate(action: () => Promise<void>) {
    setState(old => ({ ...old, busy: true, error: null }));
    try { await action(); } catch (error) {
      setState(old => ({ ...old, error: error instanceof Error ? error.message : "Operação falhou." }));
    } finally { setState(old => ({ ...old, busy: false })); }
  }

  const trade = entryType === "BUY" || entryType === "SELL";
  return <section className="portfolio-panel" aria-label="Carteira">
    <div className="portfolio-heading"><div><span className="eyebrow">FASE 16 · PORTFOLIO</span>
      <h3>Carteira manual</h3><p>Caixa, posições e P&amp;L por custo médio móvel.</p></div>
      <span className="portfolio-disclaimer">Registos manuais não são ordens, recomendações ou aprovação de risco.</span></div>
    {state.loading && <p className="portfolio-message" role="status">A consultar carteiras…</p>}
    {state.error && <p className="portfolio-message error" role="alert">{state.error}</p>}
    {!state.loading && state.portfolios.length === 0 && <form className="portfolio-create" onSubmit={event => {
      event.preventDefault(); mutate(async () => {
        const portfolio = await request("/api/market-data/portfolios", portfolioSchema, {
          method: "POST", body: JSON.stringify({ portfolio_id: crypto.randomUUID(), name,
            base_currency: currency.toUpperCase(), valuation_timeframe: timeframe }),
        });
        if (portfolioProblem(portfolio)) throw new Error("A carteira recebida é incoerente.");
        setState(old => ({ ...old, portfolios: [portfolio], selectedId: portfolio.portfolio_id }));
        await loadDashboard(portfolio, [portfolio]);
      });
    }}><label>Nome<input required maxLength={80} value={name} onChange={e => setName(e.target.value)} /></label>
      <label>Moeda-base<input required pattern="[A-Z0-9]{2,12}" maxLength={12} value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())} /></label>
      <button disabled={state.busy} type="submit">Criar carteira</button></form>}
    {selected && <><div className="portfolio-controls"><label>Carteira<select value={selected.portfolio_id}
      onChange={event => { const portfolio = state.portfolios.find(item => item.portfolio_id === event.target.value);
        if (portfolio) loadDashboard(portfolio).catch(error => setState(old => ({ ...old,
          error: error instanceof Error ? error.message : "Carteira indisponível." }))); }}>
      {state.portfolios.map(item => <option key={item.portfolio_id} value={item.portfolio_id}>{item.name} · {item.base_currency}</option>)}</select></label>
      <span>Avaliação: candles {selected.valuation_timeframe} · custo médio móvel v1</span></div>
      {state.snapshot && <><div className="portfolio-metrics">
        <div><span>Caixa</span><strong>{state.snapshot.cash_balance} {selected.base_currency}</strong></div>
        <div><span>Equity</span><strong>{state.snapshot.equity ?? "Indisponível"}</strong></div>
        <div><span>Custo das posições</span><strong>{state.snapshot.total_cost_basis}</strong></div>
        <div><span>P&amp;L não realizado</span><strong>{state.snapshot.unrealized_pnl ?? "Indisponível"}</strong></div>
        <div><span>P&amp;L realizado</span><strong>{state.snapshot.realized_pnl}</strong></div>
        <div><span>Taxas registadas</span><strong>{state.snapshot.total_fees}</strong></div>
      </div>{state.snapshot.status === "PARTIAL" && <p className="portfolio-message">Avaliação parcial: pelo menos uma posição aberta não tem preço armazenado disponível neste instante.</p>}
      <div className="table-scroll" tabIndex={0}><table><caption>Posições contabilísticas — valores exatos em {selected.base_currency}</caption>
        <thead><tr><th>Mercado</th><th>Estado</th><th>Quantidade</th><th>Custo médio</th><th>Custo</th><th>Último preço</th><th>Valor</th><th>P&amp;L não realizado</th><th>P&amp;L realizado</th></tr></thead>
        <tbody>{state.snapshot.positions.map(item => <tr key={item.market.market_id}><td><strong>{item.market.symbol}</strong><small>{item.market.market_id}</small></td>
          <td>{item.status}</td><td>{item.quantity}</td><td>{item.average_cost}</td><td>{item.cost_basis}</td>
          <td>{item.last_price ?? "—"}<small>{item.price_time ?? "Sem preço disponível"}</small></td>
          <td>{item.market_value ?? "—"}</td><td>{item.unrealized_pnl ?? "—"}</td><td>{item.realized_pnl}</td></tr>)}</tbody></table></div></>}
      <form className="portfolio-entry-form" onSubmit={event => { event.preventDefault(); mutate(async () => {
        const body = { entry_id: crypto.randomUUID(), entry_type: entryType,
          expected_revision: selected.revision, occurred_at: new Date(occurredAt + "Z").toISOString(),
          cash_amount: trade ? null : cashAmount, market_id: trade ? market?.market_id ?? null : null,
          quantity: trade ? quantity : null, unit_price: trade ? unitPrice : null,
          fee: trade ? fee : "0" };
        const result = await request(`/api/market-data/portfolios/${selected.portfolio_id}/entries`,
          portfolioEntryResultSchema, { method: "POST", body: JSON.stringify(body) });
        const portfolios = state.portfolios.map(item => item.portfolio_id === result.portfolio.portfolio_id ? result.portfolio : item);
        setCashAmount(""); setQuantity(""); setUnitPrice(""); setFee("0");
        await loadDashboard(result.portfolio, portfolios);
      }); }}><label>Tipo<select value={entryType} onChange={e => setEntryType(e.target.value as EntryType)}>
        <option value="DEPOSIT">Depósito</option><option value="WITHDRAWAL">Levantamento</option>
        <option value="BUY">Compra manual</option><option value="SELL">Venda manual</option></select></label>
        {trade ? <><label>Mercado<input readOnly value={market?.market_id ?? "Seleciona um mercado"} /></label>
          <label>Quantidade<input required type="number" min="0" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} /></label>
          <label>Preço unitário<input required type="number" min="0" step="any" value={unitPrice} onChange={e => setUnitPrice(e.target.value)} /></label>
          <label>Taxa<input required type="number" min="0" step="any" value={fee} onChange={e => setFee(e.target.value)} /></label></>
          : <label>Montante<input required type="number" min="0" step="any" value={cashAmount} onChange={e => setCashAmount(e.target.value)} /></label>}
        <label>Ocorrido em UTC<input required type="datetime-local" value={occurredAt} onChange={e => setOccurredAt(e.target.value)} /></label>
        <button type="submit" disabled={state.busy || (trade && !market)}>Registar lançamento</button></form>
      <details className="portfolio-ledger"><summary>Livro imutável · {state.entries.length} lançamentos</summary>
        {state.entries.length === 0 ? <p className="muted">Ainda não existem lançamentos.</p> : <ol>{state.entries.map(entry => <li key={entry.entry_id}>
          <strong>#{entry.sequence} · {entry.entry_type}</strong><span>{entry.market_id ?? entry.cash_amount} · efeito em caixa {entry.cash_effect} {entry.currency}</span><small>{entry.occurred_at}</small>
        </li>)}</ol>}</details>
      <PortfolioIntelligencePanel portfolio={selected} />
      <p className="portfolio-footnote">A carteira aceita apenas mercados na moeda-base e caixa financiado. Ausência de FX ou preço fica explícita; o browser não recalcula valores financeiros.</p></>}
  </section>;
}
