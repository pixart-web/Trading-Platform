"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LiveControl, requestLiveControl } from "@/lib/live-control";

export function LiveModeIndicator() {
  const [control, setControl] = useState<LiveControl | null>(null);
  useEffect(() => {
    let current = true;
    requestLiveControl().then(value => { if (current) setControl(value); }).catch(() => undefined);
    return () => { current = false; };
  }, []);
  const mode = control?.mode ?? "UNAVAILABLE";
  const dangerous = mode === "LIVE_ACTIVE" || mode === "LIVE_ARMED";
  return <Link className={`research-mode operational-mode ${dangerous ? "operational-live" : ""}`}
    href="/live-trading" aria-label={`Modo operacional: ${mode}`}>
    <i className={`status-dot ${dangerous ? "status-dot-danger" : "status-dot-safe"}`} />
    <strong>{mode}</strong>
    <span>{control?.broker ?? "NO BROKER"}</span>
    <span>{control?.account_identity_hash ? `${control.account_identity_hash.slice(0, 6)}…` : "NO ACCOUNT"}</span>
  </Link>;
}
