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
    let detail = "Unable to update the portfolio.";
    try { const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail; } catch { /* use safe fallback */ }
    throw new Error(response.status === 409 ? "The portfolio changed in another request. Refresh and retry the operation." : detail);
  }
  return schema.parse(await response.json());
}

function nowInput(): string { return new Date().toISOString().slice(0, 16); }

export function PortfolioPanel({ market, timeframe }: { market: Market | null; timeframe: Timeframe }) {
  const [state, setState] = useState<State>({ portfolios: [], selectedId: null, snapshot: null,
    entries: [], loading: true, busy: false, error: null });
  const [name, setName] = useState("Main portfolio");
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
              error: error instanceof Error ? error.message : "Portfolio unavailable." }));
          });
        }
      }).catch(error => { if (!controller.signal.aborted) setState(old => ({ ...old, loading: false,
        error: error instanceof Error ? error.message : "Portfolios unavailable." })); });
    return () => controller.abort();
  }, []);

  async function mutate(action: () => Promise<void>) {
    setState(old => ({ ...old, busy: true, error: null }));
    try { await action(); } catch (error) {
      setState(old => ({ ...old, error: error instanceof Error ? error.message : "Operation failed." }));
    } finally { setState(old => ({ ...old, busy: false })); }
  }

  const trade = entryType === "BUY" || entryType === "SELL";
  return <section className="portfolio-panel" aria-label="Portfolio">
    <div className="portfolio-heading"><div><span className="eyebrow">FASE 16 · PORTFOLIO</span>
      <h3>Manual portfolio</h3><p>Cash, positions, and P&amp;L using moving average cost.</p></div>
      <span className="portfolio-disclaimer">Manual records are not orders, recommendations, or risk approval.</span></div>
    {state.loading && <p className="portfolio-message" role="status">Loading portfolios…</p>}
    {state.error && <p className="portfolio-message error" role="alert">{state.error}</p>}
    {!state.loading && state.portfolios.length === 0 && <form className="portfolio-create" onSubmit={event => {
      event.preventDefault(); mutate(async () => {
        const portfolio = await request("/api/market-data/portfolios", portfolioSchema, {
          method: "POST", body: JSON.stringify({ portfolio_id: crypto.randomUUID(), name,
            base_currency: currency.toUpperCase(), valuation_timeframe: timeframe }),
        });
        if (portfolioProblem(portfolio)) throw new Error("The received portfolio is inconsistent.");
        setState(old => ({ ...old, portfolios: [portfolio], selectedId: portfolio.portfolio_id }));
        await loadDashboard(portfolio, [portfolio]);
      });
    }}><label>Nome<input required maxLength={80} value={name} onChange={e => setName(e.target.value)} /></label>
      <label>Moeda-base<input required pattern="[A-Z0-9]{2,12}" maxLength={12} value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())} /></label>
      <button disabled={state.busy} type="submit">Create portfolio</button></form>}
    {selected && <><div className="portfolio-controls"><label>Portfolio<select value={selected.portfolio_id}
      onChange={event => { const portfolio = state.portfolios.find(item => item.portfolio_id === event.target.value);
        if (portfolio) loadDashboard(portfolio).catch(error => setState(old => ({ ...old,
          error: error instanceof Error ? error.message : "Portfolio unavailable." }))); }}>
      {state.portfolios.map(item => <option key={item.portfolio_id} value={item.portfolio_id}>{item.name} · {item.base_currency}</option>)}</select></label>
      <span>Valuation: candles {selected.valuation_timeframe} · moving average cost v1</span></div>
      {state.snapshot && <><div className="portfolio-metrics">
        <div><span>Cash</span><strong>{state.snapshot.cash_balance} {selected.base_currency}</strong></div>
        <div><span>Equity</span><strong>{state.snapshot.equity ?? "Unavailable"}</strong></div>
        <div><span>Position cost</span><strong>{state.snapshot.total_cost_basis}</strong></div>
        <div><span>Unrealized P&amp;L</span><strong>{state.snapshot.unrealized_pnl ?? "Unavailable"}</strong></div>
        <div><span>Realized P&amp;L</span><strong>{state.snapshot.realized_pnl}</strong></div>
        <div><span>Taxas registadas</span><strong>{state.snapshot.total_fees}</strong></div>
      </div>{state.snapshot.status === "PARTIAL" && <p className="portfolio-message">Partial valuation: at least one open position has no stored price available at this instant.</p>}
      <div className="table-scroll" tabIndex={0}><table><caption>Accounting positions — exact values in {selected.base_currency}</caption>
        <thead><tr><th>Market</th><th>Status</th><th>Quantity</th><th>Average cost</th><th>Cost</th><th>Last price</th><th>Value</th><th>Unrealized P&amp;L</th><th>Realized P&amp;L</th></tr></thead>
        <tbody>{state.snapshot.positions.map(item => <tr key={item.market.market_id}><td><strong>{item.market.symbol}</strong><small>{item.market.market_id}</small></td>
          <td>{item.status}</td><td>{item.quantity}</td><td>{item.average_cost}</td><td>{item.cost_basis}</td>
          <td>{item.last_price ?? "—"}<small>{item.price_time ?? "No price available"}</small></td>
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
        <option value="DEPOSIT">Deposit</option><option value="WITHDRAWAL">Levantamento</option>
        <option value="BUY">Compra manual</option><option value="SELL">Venda manual</option></select></label>
        {trade ? <><label>Market<input readOnly value={market?.market_id ?? "Select a market"} /></label>
          <label>Quantity<input required type="number" min="0" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} /></label>
          <label>Unit price<input required type="number" min="0" step="any" value={unitPrice} onChange={e => setUnitPrice(e.target.value)} /></label>
          <label>Taxa<input required type="number" min="0" step="any" value={fee} onChange={e => setFee(e.target.value)} /></label></>
          : <label>Montante<input required type="number" min="0" step="any" value={cashAmount} onChange={e => setCashAmount(e.target.value)} /></label>}
        <label>Ocorrido em UTC<input required type="datetime-local" value={occurredAt} onChange={e => setOccurredAt(e.target.value)} /></label>
        <button type="submit" disabled={state.busy || (trade && !market)}>Record entry</button></form>
      <details className="portfolio-ledger"><summary>Immutable ledger · {state.entries.length} entries</summary>
        {state.entries.length === 0 ? <p className="muted">No entries yet.</p> : <ol>{state.entries.map(entry => <li key={entry.entry_id}>
          <strong>#{entry.sequence} · {entry.entry_type}</strong><span>{entry.market_id ?? entry.cash_amount} · efeito em caixa {entry.cash_effect} {entry.currency}</span><small>{entry.occurred_at}</small>
        </li>)}</ol>}</details>
      <PortfolioIntelligencePanel portfolio={selected} />
      <p className="portfolio-footnote">The portfolio accepts only base-currency markets and funded cash. Missing FX or price remains explicit; the browser does not recalculate financial values.</p></>}
  </section>;
}
