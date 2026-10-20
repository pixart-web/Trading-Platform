"use client";

import { useEffect, useState } from "react";

type Check = { state: "loading" | "ready" | "unavailable"; detail: string };

export default function SystemPage() {
  const [check, setCheck] = useState<Check>({ state: "loading", detail: "Loading readiness…" });
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/system/ready", { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const detail = await response.text();
        setCheck(response.ok ? { state: "ready", detail: detail || "API ready" }
          : { state: "unavailable", detail: `Readiness returned ${response.status}` });
      })
      .catch(error => {
        if (!controller.signal.aborted) setCheck({ state: "unavailable", detail: error instanceof Error ? error.message : "Dependency unavailable" });
      });
    return () => controller.abort();
  }, []);
  return <div className="capability-page">
    <header className="page-heading"><div><span className="eyebrow">OPERATIONS</span><h1>System Health</h1>
      <p>State observed through the readiness endpoint. No indicator is inferred in the browser.</p></div></header>
    <div className="capability-grid">
      <section className="terminal-card"><span className="card-kicker">APPLICATION READINESS</span>
        <h2 className={`health-${check.state}`}>{check.state === "loading" ? "Checking" : check.state === "ready" ? "Ready" : "Unavailable"}</h2>
        <pre>{check.detail}</pre></section>
      <section className="terminal-card"><span className="card-kicker">EXECUTION MODE</span><h2>Research / Paper</h2>
        <p>Live spot, live derivatives and live autopilot remain disabled by default and require independent qualifiestion.</p></section>
    </div>
  </div>;
}
