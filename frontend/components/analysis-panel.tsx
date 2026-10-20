import { analysisProblem, type AnalysisResponse, type AnalyzeHorizon } from "@/lib/analysis";

const conclusionLabels: Record<AnalyzeHorizon["conclusion"], string> = {
  ELIGIBLE_LONG: "Eligible LONG", ELIGIBLE_SHORT: "Eligible SHORT",
  INELIGIBLE_LONG: "Ineligible LONG", INELIGIBLE_SHORT: "Ineligible SHORT",
  NO_TRADE: "NO TRADE", UNAVAILABLE: "Unavailable",
};
const issueLabels: Record<string, string> = {
  FORECAST_NOT_PRODUCED: "Forecast not produced", FORECAST_UNAVAILABLE: "Forecast unavailable",
  FORECAST_EXPIRED: "Forecast expirado", FORECAST_UNCALIBRATED: "Forecast not calibrated",
  DIRECTIONAL_NOT_PRODUCED: "Directional analysis not produced", DIRECTIONAL_NO_TRADE: "No single direction",
  OPPORTUNITY_NOT_PRODUCED: "Opportunity Score not produced", OPPORTUNITY_UNAVAILABLE: "Opportunity unavailable",
  OPPORTUNITY_INELIGIBLE: "Opportunity outside economic limits",
};

type AnalysisResource = { data?: AnalysisResponse; error?: string } | null;

function EvidenceCase({ title, value }: {
  title: string; value: NonNullable<AnalyzeHorizon["directional"]>["long_case"];
}) {
  return <div className="evidence-case"><h5>{title} · {value.qualifies === null ? "unavailable" : value.qualifies ? "qualifies" : "does not qualify"}</h5>
    <ul>{value.results.map(item => <li key={item.criterion}>
      <span>{item.label}</span><strong>{item.status === "AVAILABLE"
        ? `${item.value} ${item.operator === "GREATER_THAN_OR_EQUAL" ? "≥" : "≤"} ${item.threshold}`
        : item.unavailable_reason}</strong><small>{item.status === "AVAILABLE" ? (item.passed ? "passed" : "failed") : "no evidence"}</small>
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
      <div><dt>Direction</dt><dd>{item.directional?.decision ?? "—"}</dd></div>
      <div><dt>Probabilidade calibrada</dt><dd>{item.forecast?.probability_calibration === "CALIBRATED" ? probability ?? "—" : "—"}</dd></div>
      <div><dt>Retorno esperado</dt><dd>{item.forecast?.expected_return ?? "—"}</dd></div>
      <div><dt>Net return</dt><dd>{item.opportunity?.economics?.net_expected_return ?? "—"}</dd></div>
      <div><dt>Opportunity Score</dt><dd>{item.opportunity?.score ?? "—"}</dd></div>
      <div><dt>Uncertainty</dt><dd>{item.opportunity?.economics?.uncertainty ?? "—"}</dd></div>
    </dl>
    <details className="analysis-details"><summary>Evidence, opposition and versions</summary>
      {item.directional ? <div className="evidence-grid">
        <EvidenceCase title="Caso LONG" value={item.directional.long_case} />
        <EvidenceCase title="Caso SHORT" value={item.directional.short_case} />
      </div> : <p>{item.directional_unavailable_reason}</p>}
      {item.opportunity?.exclusion_reasons.length ? <p className="analysis-exclusions">
        Failed limits: {item.opportunity.exclusion_reasons.join(" · ")}</p> : null}
      <p className="version-line">Forecast {item.forecast?.model_version ?? "—"} · Directional {item.directional?.policy_version ?? "—"} · Opportunity {item.opportunity?.policy_version ?? "—"} · Costs {item.opportunity?.cost_version ?? "—"}</p>
    </details>
  </article>;
}

export function AnalysisPanel({ result, marketId, timeframe, asOf }: {
  result: AnalysisResource; marketId: string; timeframe: string; asOf: string;
}) {
  return <section className="analysis-panel" aria-label="Shared analysis">
    <div className="analysis-title"><div><span className="eyebrow">ANALYZE · {asOf}</span><h3>Analysis by horizon</h3>
      <p>Forecast, direction, and economics in the same causal snapshot.</p></div>
      <span className="analysis-disclaimer">Scores are not probabilities or risk approval.</span></div>
    {!result && <p className="analysis-message" role="status">Loading analysis snapshot…</p>}
    {result?.error && <p className="analysis-message" role="alert">{result.error}</p>}
    {result?.data && (() => {
      const problem = analysisProblem(result.data, marketId, timeframe, asOf);
      if (problem) return <p className="analysis-message" role="alert">{problem}</p>;
      if (result.data.status === "UNAVAILABLE") return <div className="analysis-message" role="status">
        <strong>Analysis unavailable</strong><p>No stored snapshot exists for this market, timeframe, and instant.</p>
        <small>{result.data.unavailable_reason}</small></div>;
      const report = result.data.report;
      return <><div className="analysis-overview">
        <div><span>Pocket Score</span><strong>{report.pocket_score?.score ?? "—"}</strong><small>{report.pocket_score?.status ?? report.pocket_score_unavailable_reason}</small></div>
        <div><span>Coverage</span><strong>{report.status}</strong><small>{report.horizons.filter(item => item.status === "COMPLETE").length} / 13 complete horizons</small></div>
        <div><span>Version</span><strong>{report.report_version}</strong><small>Gerado {report.generated_at}</small></div>
      </div>
      <div className="analysis-horizons">{report.horizons.map(item => <HorizonCard key={item.horizon} item={item} />)}</div></>;
    })()}
  </section>;
}
