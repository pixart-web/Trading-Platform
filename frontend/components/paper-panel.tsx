"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { paperAccounts, type PaperView } from "../lib/paper";

export default function PaperPanel() {
  const [accounts, setAccounts] = useState<PaperView[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/market-data/paper/accounts", { cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("PAPER unavailable");
        const parsed = paperAccounts.parse(await response.json());
        if (!controller.signal.aborted) { setAccounts(parsed); setFailed(false); }
      }).catch(() => { if (!controller.signal.aborted) { setAccounts(null); setFailed(true); } });
    return () => controller.abort();
  }, [refresh]);
  return <main className="workspace" style={{ padding: "2rem", maxWidth: "1200px", margin: "auto" }}>
    <Link href="/">Back to market</Link>
    <h1>PAPER — simulated execution</h1>
    <p role="note">Simulated capital, orders, and results. No orders are sent to a real broker. No profitability claim.</p>
    <button type="button" onClick={() => setRefresh(value => value + 1)}>Refresh PAPER accounts</button>
    {failed ? <p role="alert">PAPER unavailable: the journal and accounting could not be validated.</p>
      : accounts === null ? <p role="status">Loading PAPER accounts…</p>
      : accounts.length === 0 ? <p>No PAPER account is registered. Creation requires explicit configuration by the local operator.</p>
      : accounts.map(view => <section key={view.state.account_id} style={{ marginTop: "2rem" }}>
        <h2>{view.state.market_id} · PAPER</h2>
        <p>{view.state.origin === "REAL" ? "Real market data · simulated execution" : "Synthetic data · simulated execution"}</p>
        <p>State at observation: {view.state.status} · Revision: {view.state.revision} · {view.ready ? "PAPER ready" : `PAPER not ready: ${view.readiness_reason ?? view.state.reason ?? "no data"}`}</p>
        <p>Observed: {view.observed_at} · Last candle: {view.state.last_close ?? "unavailable"}</p>
        <dl>
          <dt>Simulated cash ({view.state.quote_currency})</dt><dd>{view.state.portfolio.cash}</dd>
          <dt>Simulated quantity</dt><dd>{view.state.portfolio.quantity}</dd>
          <dt>Simulated equity</dt><dd>{view.state.portfolio.equity}</dd>
          <dt>Reserved cash</dt><dd>{view.state.portfolio.reserved_cash}</dd>
          <dt>Simulated realized PnL</dt><dd>{view.state.realized_pnl}</dd>
          <dt>Simulated unrealized PnL</dt><dd>{view.state.unrealized_pnl ?? "unavailable"}</dd>
          <dt>Fees simuladas</dt><dd>{view.state.total_fees}</dd>
        </dl>
        <h3>Simulated orders ({view.state.pending.length} pending)</h3>
        <ul>{view.state.orders.slice(-50).map((order, i) => <li key={i}>{order.at} · {order.client_id} · {order.state} · {order.reason}</li>)}</ul>
        <h3>Fills simulados</h3>
        <ul>{view.state.fills.slice(-50).map((fill, i) => <li key={i}>{fill.at} · {fill.client_id} · {fill.quantity} @ {fill.price} · fee {fill.fee}</li>)}</ul>
      </section>)}
  </main>;
}
