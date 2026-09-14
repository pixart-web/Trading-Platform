import { analysisProblem, type AnalysisResponse, type AnalyzeHorizon } from "@/lib/analysis";

const conclusionLabels: Record<AnalyzeHorizon["conclusion"], string> = {
  ELIGIBLE_LONG: "LONG elegível", ELIGIBLE_SHORT: "SHORT elegível",
  INELIGIBLE_LONG: "LONG inelegível", INELIGIBLE_SHORT: "SHORT inelegível",
  NO_TRADE: "NO TRADE", UNAVAILABLE: "Indisponível",
};
const issueLabels: Record<string, string> = {
  FORECAST_NOT_PRODUCED: "Forecast não produzido", FORECAST_UNAVAILABLE: "Forecast indisponível",
  FORECAST_EXPIRED: "Forecast expirado", FORECAST_UNCALIBRATED: "Forecast não calibrado",
  DIRECTIONAL_NOT_PRODUCED: "Análise direcional não produzida", DIRECTIONAL_NO_TRADE: "Sem direção única",
  OPPORTUNITY_NOT_PRODUCED: "Opportunity Score não produzido", OPPORTUNITY_UNAVAILABLE: "Oportunidade indisponível",
  OPPORTUNITY_INELIGIBLE: "Oportunidade fora dos limites económicos",
};

type AnalysisResource = { data?: AnalysisResponse; error?: string } | null;

function EvidenceCase({ title, value }: {
  title: string; value: NonNullable<AnalyzeHorizon["directional"]>["long_case"];
}) {
  return <div className="evidence-case"><h5>{title} · {value.qualifies === null ? "indisponível" : value.qualifies ? "qualifica" : "não qualifica"}</h5>
    <ul>{value.results.map(item => <li key={item.criterion}>
      <span>{item.label}</span><strong>{item.status === "AVAILABLE"
        ? `${item.value} ${item.operator === "GREATER_THAN_OR_EQUAL" ? "≥" : "≤"} ${item.threshold}`
        : item.unavailable_reason}</strong><small>{item.status === "AVAILABLE" ? (item.passed ? "passou" : "falhou") : "sem evidência"}</small>
    </li>)}</ul></div>;
}

function HorizonCard({ item }: { item: AnalyzeHorizon }) {
  const probabilityDirection = item.directional?.decision === "LONG" ? "UP"
    : item.directional?.decision === "SHORT" ? "DOWN" : item.forecast?.direction;
  const probability = item.forecast?.probabilities.find(value => value.direction === probabilityDirection)?.probability;
  return <article className="analysis-horizon">
    <div className="horizon-heading"><div><span className="horizon-name">{item.horizon}</span>
      <strong>{conclusionLabels[item.conclusion]}</strong></div>
      <span className={`analysis-state state-${item.status.toLowerCase()}`}>{item.status}</span></div>
    {item.issues.length > 0 && <ul className="analysis-issues">{item.issues.map(issue =>
      <li key={issue}>{issueLabels[issue] ?? issue}</li>)}</ul>}
    <dl className="analysis-metrics">
      <div><dt>Direção</dt><dd>{item.directional?.decision ?? "—"}</dd></div>
      <div><dt>Probabilidade calibrada</dt><dd>{item.forecast?.probability_calibration === "CALIBRATED" ? probability ?? "—" : "—"}</dd></div>
      <div><dt>Retorno esperado</dt><dd>{item.forecast?.expected_return ?? "—"}</dd></div>
      <div><dt>Retorno líquido</dt><dd>{item.opportunity?.economics?.net_expected_return ?? "—"}</dd></div>
      <div><dt>Opportunity Score</dt><dd>{item.opportunity?.score ?? "—"}</dd></div>
      <div><dt>Incerteza</dt><dd>{item.opportunity?.economics?.uncertainty ?? "—"}</dd></div>
    </dl>
    <details className="analysis-details"><summary>Evidência, oposição e versões</summary>
      {item.directional ? <div className="evidence-grid">
        <EvidenceCase title="Caso LONG" value={item.directional.long_case} />
        <EvidenceCase title="Caso SHORT" value={item.directional.short_case} />
      </div> : <p>{item.directional_unavailable_reason}</p>}
      {item.opportunity?.exclusion_reasons.length ? <p className="analysis-exclusions">
        Limites falhados: {item.opportunity.exclusion_reasons.join(" · ")}</p> : null}
      <p className="version-line">Forecast {item.forecast?.model_version ?? "—"} · Direcional {item.directional?.policy_version ?? "—"} · Oportunidade {item.opportunity?.policy_version ?? "—"} · Custos {item.opportunity?.cost_version ?? "—"}</p>
    </details>
  </article>;
}

export function AnalysisPanel({ result, marketId, timeframe, asOf }: {
  result: AnalysisResource; marketId: string; timeframe: string; asOf: string;
}) {
  return <section className="analysis-panel" aria-label="Análise partilhada">
    <div className="analysis-title"><div><span className="eyebrow">ANALYZE · {asOf}</span><h3>Análise por horizonte</h3>
      <p>Forecast, direção e economia no mesmo snapshot causal.</p></div>
      <span className="analysis-disclaimer">Índices não são probabilidades nem aprovação de risco.</span></div>
    {!result && <p className="analysis-message" role="status">A consultar o snapshot de análise…</p>}
    {result?.error && <p className="analysis-message" role="alert">{result.error}</p>}
    {result?.data && (() => {
      const problem = analysisProblem(result.data, marketId, timeframe, asOf);
      if (problem) return <p className="analysis-message" role="alert">{problem}</p>;
      if (result.data.status === "UNAVAILABLE") return <div className="analysis-message" role="status">
        <strong>Análise indisponível</strong><p>Não existe um snapshot armazenado para este mercado, timeframe e instante.</p>
        <small>{result.data.unavailable_reason}</small></div>;
      const report = result.data.report;
      return <><div className="analysis-overview">
        <div><span>Pocket Score</span><strong>{report.pocket_score?.score ?? "—"}</strong><small>{report.pocket_score?.status ?? report.pocket_score_unavailable_reason}</small></div>
        <div><span>Cobertura</span><strong>{report.status}</strong><small>{report.horizons.filter(item => item.status === "COMPLETE").length} / 13 horizontes completos</small></div>
        <div><span>Versão</span><strong>{report.report_version}</strong><small>Gerado {report.generated_at}</small></div>
      </div>
      <div className="analysis-horizons">{report.horizons.map(item => <HorizonCard key={item.horizon} item={item} />)}</div></>;
    })()}
  </section>;
}
