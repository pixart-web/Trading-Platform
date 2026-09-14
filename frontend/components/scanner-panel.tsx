"use client";

import { useState } from "react";
import type { Timeframe } from "@/lib/market-data";
import { horizons } from "@/lib/analysis";
import { scanProblem, scanReportSchema, type ScanReport } from "@/lib/scanner";

type OptionalNumber = "" | string;
const reasonLabels: Record<string, string> = {
  NO_ANALYZE_REPORT: "Sem relatório Analyze", REPORT_UNAVAILABLE_AT_SCAN: "Relatório ainda indisponível",
  OPPORTUNITY_NOT_PRODUCED: "Oportunidade não produzida", OPPORTUNITY_UNAVAILABLE: "Oportunidade indisponível",
  OPPORTUNITY_INELIGIBLE: "Oportunidade inelegível", DIRECTION_FILTERED: "Direção excluída",
  SCORE_BELOW_MINIMUM: "Índice abaixo do mínimo", NET_RETURN_BELOW_MINIMUM: "Retorno líquido abaixo do mínimo",
  LIQUIDITY_BELOW_MINIMUM: "Liquidez abaixo do mínimo", UNCERTAINTY_ABOVE_MAXIMUM: "Incerteza acima do máximo",
  RISK_REWARD_BELOW_MINIMUM: "Risco/retorno abaixo do mínimo", COST_ABOVE_MAXIMUM: "Custo acima do máximo",
  POLICY_RESULT_LIMIT: "Fora do limite desta política",
};

async function errorMessage(response: Response): Promise<string> {
  try { const body = await response.json() as { detail?: unknown }; if (typeof body.detail === "string") return body.detail; }
  catch { /* the status text remains the honest fallback */ }
  return `Pedido recusado (${response.status}).`;
}

export function ScannerPanel({ timeframe, asOf }: { timeframe: Timeframe; asOf: string }) {
  const [horizon, setHorizon] = useState<typeof horizons[number]>("24H");
  const [assetType, setAssetType] = useState("");
  const [direction, setDirection] = useState("");
  const [minimumScore, setMinimumScore] = useState<OptionalNumber>("");
  const [minimumNetReturn, setMinimumNetReturn] = useState<OptionalNumber>("");
  const [minimumLiquidity, setMinimumLiquidity] = useState<OptionalNumber>("");
  const [maximumUncertainty, setMaximumUncertainty] = useState<OptionalNumber>("");
  const [limit, setLimit] = useState("100");
  const [report, setReport] = useState<ScanReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true); setError(null); setReport(null);
    const nullable = (value: string) => value === "" ? null : value;
    const request = {
      schema_version: "scan-request-1.0.0", scan_id: crypto.randomUUID(), candle_timeframe: timeframe,
      horizon, as_of: asOf, scanner_version: "scanner-1.0.0",
      filters: { asset_types: assetType ? [assetType] : [], venue_ids: [], quote_currencies: [], market_ids: [],
        directions: direction ? [direction] : ["LONG", "SHORT"], minimum_score: nullable(minimumScore),
        minimum_net_return: nullable(minimumNetReturn), minimum_liquidity: nullable(minimumLiquidity),
        maximum_uncertainty: nullable(maximumUncertainty), minimum_risk_reward: null,
        maximum_total_cost: null, max_results_per_policy: Number(limit) },
    };
    try {
      const response = await fetch("/api/market-data/scans", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
      if (!response.ok) throw new Error(await errorMessage(response));
      const parsed = scanReportSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("O serviço devolveu um scan com formato inválido.");
      const problem = scanProblem(parsed.data, timeframe, horizon, asOf);
      if (problem) throw new Error(problem);
      setReport(parsed.data);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Não foi possível executar o scan."); }
    finally { setLoading(false); }
  }

  return <section className="scanner-panel" aria-label="Scanner de oportunidades">
    <div className="scanner-heading"><div><span className="eyebrow">FASE 15 · SCANNER</span>
      <h3>Comparar oportunidades armazenadas</h3>
      <p>Filtra relatórios Analyze com o mesmo timeframe, horizonte e instante UTC.</p></div>
      <span className="scanner-disclaimer">Índices não são probabilidades, recomendações ou aprovação de risco.</span></div>
    <div className="scanner-controls">
      <label>Horizonte<select value={horizon} onChange={event => setHorizon(event.target.value as typeof horizon)}>
        {horizons.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Classe<select value={assetType} onChange={event => setAssetType(event.target.value)}>
        <option value="">Todas</option><option>CRYPTO</option><option>STOCK</option><option>ETF</option><option>INDEX</option></select></label>
      <label>Direção<select value={direction} onChange={event => setDirection(event.target.value)}>
        <option value="">LONG e SHORT</option><option>LONG</option><option>SHORT</option></select></label>
      <label>Índice mínimo<input aria-label="Índice mínimo" type="number" min="0" max="100" step="0.01" value={minimumScore} onChange={e => setMinimumScore(e.target.value)} /></label>
      <label>Retorno líquido mínimo<input aria-label="Retorno líquido mínimo" type="number" step="0.0001" value={minimumNetReturn} onChange={e => setMinimumNetReturn(e.target.value)} /></label>
      <label>Liquidez mínima<input aria-label="Liquidez mínima" type="number" min="0" max="1" step="0.01" value={minimumLiquidity} onChange={e => setMinimumLiquidity(e.target.value)} /></label>
      <label>Incerteza máxima<input aria-label="Incerteza máxima" type="number" min="0" max="1" step="0.01" value={maximumUncertainty} onChange={e => setMaximumUncertainty(e.target.value)} /></label>
      <label>Máximo / política<input aria-label="Máximo por política" type="number" min="1" max="250" step="1" required value={limit} onChange={e => setLimit(e.target.value)} /></label>
      <button className="secondary" type="button" disabled={loading || Number(limit) < 1 || Number(limit) > 250} onClick={run}>
        {loading ? "A executar…" : "Executar scan"}</button>
    </div>
    {error && <p className="scanner-message error" role="alert">{error}</p>}
    {report && <div className="scanner-results" aria-live="polite">
      <div className="scanner-summary"><strong>{report.status === "RESULTS" ? `${report.groups.reduce((n, g) => n + g.entries.length, 0)} resultados` : "Sem correspondências"}</strong>
        <span>{report.analyze_reports_found} relatórios encontrados em {report.universe_size} mercados · {report.horizon} · {report.candle_timeframe}</span></div>
      {report.status === "NO_MATCHES" && <p className="scanner-message">Nenhuma oportunidade armazenada cumpre estes filtros. As exclusões abaixo explicam o universo completo.</p>}
      {report.groups.map(group => <section className="scanner-group" key={group.policy_version + group.policy_hash}>
        <h4>Política {group.policy_version}</h4><small>Comparação isolada · hash {group.policy_hash.slice(0, 12)}…</small>
        <div className="table-scroll" tabIndex={0}><table><caption>Ranking por índice explicável</caption><thead><tr>
          <th>Posição</th><th>Mercado</th><th>Direção</th><th>Índice / 100</th><th>Retorno líquido</th><th>Liquidez</th><th>Incerteza</th><th>Risco/retorno</th><th>Custo</th>
        </tr></thead><tbody>{group.entries.map(entry => <tr key={entry.opportunity.opportunity_id}>
          <td>{entry.rank}</td><td><strong>{entry.market.symbol}</strong><small>{entry.market.market_id} · {entry.market.venue_id}</small></td>
          <td>{entry.opportunity.direction}</td><td>{entry.opportunity.score}</td><td>{entry.opportunity.economics?.net_expected_return}</td>
          <td>{entry.opportunity.economics?.liquidity}</td><td>{entry.opportunity.economics?.uncertainty}</td>
          <td>{entry.opportunity.economics?.risk_reward}</td><td>{entry.opportunity.economics?.total_cost_rate}</td>
        </tr>)}</tbody></table></div></section>)}
      <details className="scanner-exclusions"><summary>Exclusões explícitas · {report.excluded.length}</summary>
        {report.excluded.length === 0 ? <p>Nenhum mercado excluído.</p> : <ul>{report.excluded.map(item => <li key={item.market.market_id}>
          <strong>{item.market.symbol}</strong><span>{item.market.market_id}</span>
          <span>{item.reasons.map(reason => reasonLabels[reason] ?? reason).join(" · ")}</span>
          {item.opportunity?.exclusion_reasons.length ? <small>Política da oportunidade: {item.opportunity.exclusion_reasons.join(" · ")}</small> : null}
        </li>)}</ul>}
      </details>
      <p className="version-line">Scan {report.scan_id} · {report.scanner_version} · gerado {report.generated_at}</p>
    </div>}
  </section>;
}
