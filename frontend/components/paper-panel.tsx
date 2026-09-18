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
    <Link href="/">Voltar ao mercado</Link>
    <h1>PAPER — execução simulada</h1>
    <p role="note">Capital, ordens e resultados simulados. Nenhuma ordem é enviada a um broker real. Sem alegação de rentabilidade.</p>
    <button type="button" onClick={() => setRefresh(value => value + 1)}>Atualizar contas PAPER</button>
    {failed ? <p role="alert">PAPER indisponível: não foi possível validar o journal e a contabilidade.</p>
      : accounts === null ? <p role="status">A consultar contas PAPER…</p>
      : accounts.length === 0 ? <p>Nenhuma conta PAPER registada. A criação exige configuração explícita pelo operador local.</p>
      : accounts.map(view => <section key={view.state.account_id} style={{ marginTop: "2rem" }}>
        <h2>{view.state.market_id} · PAPER</h2>
        <p>{view.state.origin === "REAL" ? "Dados de mercado reais · execução simulada" : "Dados sintéticos · execução simulada"}</p>
        <p>Estado à observação: {view.state.status} · Revisão: {view.state.revision} · {view.ready ? "PAPER pronto" : `PAPER não pronto: ${view.readiness_reason ?? view.state.reason ?? "sem dados"}`}</p>
        <p>Observado: {view.observed_at} · Último candle: {view.state.last_close ?? "indisponível"}</p>
        <dl>
          <dt>Caixa simulada ({view.state.quote_currency})</dt><dd>{view.state.portfolio.cash}</dd>
          <dt>Quantidade simulada</dt><dd>{view.state.portfolio.quantity}</dd>
          <dt>Equity simulada</dt><dd>{view.state.portfolio.equity}</dd>
          <dt>Caixa reservada</dt><dd>{view.state.portfolio.reserved_cash}</dd>
          <dt>PnL realizado simulado</dt><dd>{view.state.realized_pnl}</dd>
          <dt>PnL não realizado simulado</dt><dd>{view.state.unrealized_pnl ?? "indisponível"}</dd>
          <dt>Fees simuladas</dt><dd>{view.state.total_fees}</dd>
        </dl>
        <h3>Ordens simuladas ({view.state.pending.length} pendentes)</h3>
        <ul>{view.state.orders.slice(-50).map((order, i) => <li key={i}>{order.at} · {order.client_id} · {order.state} · {order.reason}</li>)}</ul>
        <h3>Fills simulados</h3>
        <ul>{view.state.fills.slice(-50).map((fill, i) => <li key={i}>{fill.at} · {fill.client_id} · {fill.quantity} @ {fill.price} · fee {fill.fee}</li>)}</ul>
      </section>)}
  </main>;
}
