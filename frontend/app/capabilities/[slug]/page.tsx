import Link from "next/link";
import { notFound } from "next/navigation";

const capabilities = {
  strategies: {
    title: "Strategies", status: "Read-only catalogue",
    endpoint: "GET /api/v1/strategies", tone: "available",
    summary: "Versioned strategy specifications can be inspected through the backend catalogue. Lifecycle mutation is not exposed because no authorized HTTP contract exists.",
    boundary: "A strategy cannot reach a broker. Every executable intent must pass portfolio, risk, leverage assessment and execution controls.",
  },
  backtesting: {
    title: "Backtesting", status: "Stored runs only",
    endpoint: "GET /api/v1/backtests/{run_id}", tone: "limited",
    summary: "The application can retrieve a known immutable backtest run. Job creation is unavailable until an authenticated scheduling contract is implemented.",
    boundary: "Final holdouts remain protected and stored scores are never presented as calibrated probabilities.",
  },
  research: {
    title: "Research Factory", status: "Artifact inspection",
    endpoint: "GET /api/v1/research/reports/{report_id} · GET /api/v1/research/models/{artifact_id}", tone: "limited",
    summary: "Immutable reports and versioned model artifacts are retrievable by identifier. There is no browser-side model training or research orchestration.",
    boundary: "Datasets, features, scores and model artifacts retain independent versions and temporal evidence.",
  },
  execution: {
    title: "Execution", status: "Live submission unavailable",
    endpoint: "No public live-order HTTP endpoint", tone: "blocked",
    summary: "Paper and qualifiestion engines exist behind the application boundary. Real submission remains structurally unavailable without a selected venue, qualified credentials and separate operator authorization.",
    boundary: "LIVE_SPOT_ENABLED=false · LIVE_DERIVATIVES_ENABLED=false · unknown orders require reconciliation before retry.",
  },
  risk: {
    title: "Risk", status: "Server-side boundary",
    endpoint: "No standalone public mutation endpoint", tone: "available",
    summary: "Risk decisions are evaluated inside the ordered trading pipeline and recorded with their evidence. The browser cannot manufacture or override approval.",
    boundary: "Missing data, stale prices, inconsistent portfolios, breached limits or unavailable dependencies fail closed.",
  },
} as const;

export function generateStaticParams() {
  return Object.keys(capabilities).map(slug => ({ slug }));
}

export default async function CapabilityPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = capabilities[slug as keyof typeof capabilities];
  if (!item) notFound();
  return <div className="capability-page">
    <header className="page-heading"><div><span className="eyebrow">OPERATIONAL CAPABILITY</span><h1>{item.title}</h1>
      <p>{item.summary}</p></div><span className={`capability-state ${item.tone}`}>{item.status}</span></header>
    <div className="capability-grid">
      <section className="terminal-card"><span className="card-kicker">BACKEND CONTRACT</span><h2>{item.endpoint}</h2>
        <p>Requests use the shared authenticated API boundary. Provider and validation failures remain visible to the operator.</p></section>
      <section className="terminal-card"><span className="card-kicker">SAFETY BOUNDARY</span><h2>Fail-closed</h2><p>{item.boundary}</p></section>
      <section className="terminal-card capability-actions"><span className="card-kicker">AVAILABLE ACTION</span>
        <h2>Continue in the operational workspace</h2><p>Use the integrated dashboard for real market, analysis, watchlist, scanner and portfolio workflows.</p>
        <Link className="action-link" href="/">Open Market Intelligence →</Link></section>
    </div>
  </div>;
}
