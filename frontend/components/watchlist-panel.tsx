"use client";

import { useEffect, useState } from "react";
import { z } from "zod";
import type { Market, Timeframe } from "@/lib/market-data";
import {
  alertsSchema, nullableSnapshotSchema, snapshotProblem, snapshotResultSchema,
  watchlistProblem, watchlistSchema, watchlistsSchema, type Watchlist,
  type WatchlistAlert, type WatchlistSnapshot,
} from "@/lib/watchlists";

type State = {
  lists: Watchlist[]; selectedId: string | null; snapshot: WatchlistSnapshot | null;
  alerts: WatchlistAlert[]; loading: boolean; busy: boolean; error: string | null;
};

async function request<T>(url: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store", headers: {
    "Content-Type": "application/json", ...(init?.headers ?? {}),
  } });
  if (!response.ok) throw new Error(response.status === 409
    ? "A lista mudou noutro pedido. Atualiza e repete a operação."
    : "Não foi possível atualizar a watchlist.");
  return schema.parse(await response.json());
}

const label: Record<string, string> = {
  ANALYSIS_BECAME_AVAILABLE: "Análise passou a estar disponível",
  ANALYSIS_BECAME_UNAVAILABLE: "Análise deixou de estar disponível",
  HORIZON_CONCLUSION_CHANGED: "Conclusão alterada",
};

export function WatchlistPanel({ market, timeframe, asOf }: {
  market: Market | null; timeframe: Timeframe; asOf: string;
}) {
  const [state, setState] = useState<State>({ lists: [], selectedId: null, snapshot: null,
    alerts: [], loading: true, busy: false, error: null });
  const selected = state.lists.find(item => item.watchlist_id === state.selectedId) ?? null;

  async function loadHistory(id: string, lists = state.lists) {
    const [snapshot, alerts] = await Promise.all([
      request(`/api/market-data/watchlists/${id}/snapshots/latest`, nullableSnapshotSchema),
      request(`/api/market-data/watchlists/${id}/alerts?limit=40`, alertsSchema),
    ]);
    const list = lists.find(item => item.watchlist_id === id);
    const problem = snapshot && list ? snapshotProblem(snapshot, list) : null;
    setState(old => ({ ...old, selectedId: id, snapshot: problem ? null : snapshot, alerts,
      error: problem, loading: false }));
  }

  useEffect(() => {
    const controller = new AbortController();
    request("/api/market-data/watchlists", watchlistsSchema, { signal: controller.signal })
      .then(lists => {
        if (controller.signal.aborted) return;
        const first = lists[0]?.watchlist_id ?? null;
        setState(old => ({ ...old, lists, selectedId: first, loading: false }));
        if (first) Promise.all([
          request(`/api/market-data/watchlists/${first}/snapshots/latest`, nullableSnapshotSchema,
            { signal: controller.signal }),
          request(`/api/market-data/watchlists/${first}/alerts?limit=40`, alertsSchema,
            { signal: controller.signal }),
        ]).then(([snapshot, alerts]) => {
          if (controller.signal.aborted) return;
          const list = lists[0];
          const problem = snapshot && list ? snapshotProblem(snapshot, list) : null;
          setState(old => ({ ...old, snapshot: problem ? null : snapshot, alerts, error: problem }));
        }).catch(error => {
          if (!controller.signal.aborted) setState(old => ({ ...old, loading: false,
            error: error instanceof Error ? error.message : "Watchlist indisponível." }));
        });
      }).catch(error => {
        if (!controller.signal.aborted) setState(old => ({ ...old, loading: false,
          error: error instanceof Error ? error.message : "Watchlists indisponíveis." }));
      });
    return () => controller.abort();
  }, []);

  async function mutate(action: () => Promise<void>) {
    setState(old => ({ ...old, busy: true, error: null }));
    try { await action(); } catch (error) {
      setState(old => ({ ...old, error: error instanceof Error ? error.message : "Operação falhou." }));
    } finally { setState(old => ({ ...old, busy: false })); }
  }

  const member = market && selected?.members.find(item => item.market_id === market.market_id);
  return <section className="watchlist-panel" aria-label="Watchlists">
    <div className="watchlist-heading"><div><span className="eyebrow">WATCHLISTS · SNAPSHOTS</span>
      <h3>A acompanhar</h3><p>Listas persistentes e mudanças observadas na análise armazenada.</p></div>
      {selected && <button className="secondary" disabled={state.busy} onClick={() => mutate(async () => {
        const result = await request(`/api/market-data/watchlists/${selected.watchlist_id}/snapshots`,
          snapshotResultSchema, { method: "POST", body: JSON.stringify({ snapshot_id: crypto.randomUUID(), as_of: asOf }) });
        setState(old => ({ ...old, snapshot: result.snapshot,
          alerts: [...result.events].reverse().concat(old.alerts).slice(0, 40) }));
      })}>Registar snapshot</button>}
    </div>
    {state.loading && <p role="status" className="watchlist-message">A consultar watchlists…</p>}
    {state.error && <p role="alert" className="watchlist-message">{state.error}</p>}
    {!state.loading && state.lists.length === 0 && <div className="watchlist-message">
      <strong>Ainda não há listas</strong><p>Cria uma lista para guardar mercados e comparar snapshots Analyze.</p>
      <button disabled={state.busy} onClick={() => mutate(async () => {
        const list = await request("/api/market-data/watchlists", watchlistSchema, {
          method: "POST", body: JSON.stringify({ watchlist_id: crypto.randomUUID(), name: "A acompanhar" }),
        });
        if (watchlistProblem(list)) throw new Error("A lista recebida é incoerente.");
        setState(old => ({ ...old, lists: [list], selectedId: list.watchlist_id }));
      })}>Criar watchlist</button></div>}
    {selected && <><div className="watchlist-controls">
      <label>Lista<select value={selected.watchlist_id} onChange={event => {
        loadHistory(event.target.value).catch(error => setState(old => ({ ...old,
          error: error instanceof Error ? error.message : "Watchlist indisponível." })));
      }}>{state.lists.map(item => <option key={item.watchlist_id} value={item.watchlist_id}>
        {item.name} · {item.members.length}</option>)}</select></label>
      {market && <button disabled={state.busy} onClick={() => mutate(async () => {
        const url = `/api/market-data/watchlists/${selected.watchlist_id}/markets/${encodeURIComponent(market.market_id)}`;
        const list = await request(member ? `${url}?expected_revision=${selected.revision}` : url,
          watchlistSchema, member ? { method: "DELETE" } : { method: "PUT", body: JSON.stringify({
            member_id: crypto.randomUUID(), candle_timeframe: timeframe, expected_revision: selected.revision,
          }) });
        setState(old => ({ ...old, lists: old.lists.map(item => item.watchlist_id === list.watchlist_id ? list : item) }));
      })}>{member ? "Remover mercado" : "Adicionar mercado"}</button>}
    </div>
    <div className="watchlist-grid"><div><h4>Mercados guardados</h4>
      {selected.members.length === 0 ? <p className="muted">Seleciona um mercado e adiciona-o à lista.</p>
        : <ul className="watchlist-members">{selected.members.map(item => <li key={item.member_id}>
          <strong>{item.market_id}</strong><span>{item.candle_timeframe} · desde {item.added_at}</span>
        </li>)}</ul>}</div><div><h4>Último snapshot</h4>
      {!state.snapshot ? <p className="muted">Ainda não foi registado um snapshot.</p>
        : <><p><strong>{state.snapshot.status}</strong> · revisão {state.snapshot.watchlist_revision}<br />
          <small>{state.snapshot.as_of}</small></p><ul className="snapshot-items">{state.snapshot.items.map(item => <li key={item.member_id}>
            <strong>{item.market_id}</strong><span>{item.report_status ?? item.unavailable_reason}</span>
            <small>{item.horizons.filter(value => value.conclusion.startsWith("ELIGIBLE_")).length} horizontes elegíveis</small>
          </li>)}</ul></>}</div></div>
    <details className="watchlist-events"><summary>Eventos observados · {state.alerts.length}</summary>
      {state.alerts.length === 0 ? <p className="muted">Sem transições entre snapshots.</p>
        : <ol>{state.alerts.map(event => <li key={event.event_id}><strong>{event.market_id}</strong>
          <span>{label[event.event_type] ?? event.event_type}{event.horizon ? ` · ${event.horizon}` : ""}</span>
          {event.previous_conclusion && <small>{event.previous_conclusion} → {event.current_conclusion}</small>}</li>)}</ol>}
    </details><p className="watchlist-disclaimer">Os eventos registam mudanças em artefactos armazenados. Não são alertas de preço, recomendações ou aprovação de risco.</p></>}
  </section>;
}