"use client";

import { useEffect, useState } from "react";
import type { Portfolio } from "@/lib/portfolio";
import {
  intelligenceProblem, portfolioIntelligenceListSchema, portfolioIntelligenceSchema,
  type PortfolioIntelligence,
} from "@/lib/portfolio-intelligence";

async function parseResponse(response: Response): Promise<unknown> {
  if (response.ok) return response.json();
  let message = "Não foi possível gerar a inteligência da carteira.";
  try {
    const value = await response.json() as { detail?: unknown };
    if (typeof value.detail === "string") message = value.detail;
  } catch { /* safe fallback */ }
  throw new Error(message);
}

function metric(value: PortfolioIntelligence["portfolio_per_bar_volatility"]): string {
  return value.status === "AVAILABLE" ? value.value! : "Indisponível · " + value.reason;
}

export function PortfolioIntelligencePanel({ portfolio }: { portfolio: Portfolio }) {
  const [report, setReport] = useState<PortfolioIntelligence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/market-data/portfolios/" + portfolio.portfolio_id + "/intelligence?limit=1",
      { cache: "no-store", signal: controller.signal })
      .then(parseResponse).then(value => portfolioIntelligenceListSchema.parse(value))
      .then(reports => {
        if (controller.signal.aborted) return;
        const latest = reports[0] ?? null;
        const problem = latest ? intelligenceProblem(latest, portfolio) : null;
        setReport(problem ? null : latest);
        setError(problem);
      }).catch(reason => {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : "Inteligência indisponível.");
      });
    return () => controller.abort();
  }, [portfolio]);

  async function generate() {
    setBusy(true); setError(null);
    try {
      const response = await fetch(
        "/api/market-data/portfolios/" + portfolio.portfolio_id + "/intelligence",
        { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ analysis_id: crypto.randomUUID(), as_of: new Date().toISOString() }) },
      );
      const value = portfolioIntelligenceSchema.parse(await parseResponse(response));
      const problem = intelligenceProblem(value, portfolio);
      if (problem) throw new Error(problem);
      setReport(value);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Inteligência indisponível.");
    } finally { setBusy(false); }
  }

  return <section className="portfolio-intelligence" aria-label="Inteligência da carteira">
    <div className="portfolio-intelligence-heading"><div>
      <span className="eyebrow">FASE 17 · INTELIGÊNCIA</span>
      <h4>Exposição e risco observado</h4>
    </div><button type="button" disabled={busy} onClick={generate}>
      {busy ? "A calcular…" : "Registar análise"}
    </button></div>
    <p className="portfolio-footnote">Observações explicáveis sobre dados causais armazenados. Não geram recomendações, risco aprovado ou ordens.</p>
    {error && <p className="portfolio-message error" role="alert">{error}</p>}
    {!report && !error && <p className="muted">Ainda não existe uma análise imutável desta carteira.</p>}
    {report && <><div className="portfolio-metrics">
      <div><span>Volatilidade por barra</span><strong>{metric(report.portfolio_per_bar_volatility)}</strong></div>
      <div><span>Beta</span><strong>{metric(report.portfolio_beta)}</strong></div>
      <div><span>Drawdown</span><strong>{metric(report.drawdown)}</strong></div>
      <div><span>Liquidez</span><strong>{metric(report.liquidity)}</strong></div>
    </div>
    <div className="table-scroll" tabIndex={0}><table>
      <caption>Alocação atual — valores exatos</caption>
      <thead><tr><th>Dimensão</th><th>Grupo</th><th>Valor</th><th>Peso</th></tr></thead>
      <tbody>{report.allocations.map(item => <tr key={item.dimension + item.key}>
        <td>{item.dimension}</td><td>{item.key}</td><td>{item.value}</td>
        <td>{item.portfolio_weight}</td></tr>)}</tbody>
    </table></div>
    <details><summary>Observações e indisponibilidades</summary>
      <ul>{report.observations.map(item => <li key={item.code}>
        <strong>{item.code}</strong> · {item.message}
      </li>)}
      <li><strong>SECTOR</strong> · {report.sector_concentration.explanation}</li>
      <li><strong>REGIME</strong> · {report.regime_exposure.explanation}</li>
      <li><strong>HORIZON</strong> · {report.horizon_exposure.explanation}</li></ul>
    </details></>}
  </section>;
}
