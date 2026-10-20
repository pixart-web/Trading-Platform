"use client";

import { FormEvent, useEffect, useState } from "react";
import { LiveControl, requestLiveControl } from "@/lib/live-control";

const actions = ["ENABLE_PAPER", "ARM_LIVE", "ACTIVATE_LIVE", "DISABLE_LIVE",
  "HALT_NEW_ORDERS", "ACTIVATE_KILL_SWITCH", "RESET_KILL_SWITCH"] as const;
const moneyFields = ["capital_limit", "order_notional_limit", "total_exposure_limit",
  "position_notional_limit", "strategy_exposure_limit", "broker_exposure_limit",
  "asset_exposure_limit", "daily_loss_limit"] as const;
const fractionFields = ["maximum_drawdown", "maximum_slippage_fraction",
  "maximum_spread_fraction", "maximum_price_deviation_fraction"] as const;
const countFields = ["maximum_positions", "maximum_orders_per_minute", "maximum_orders_per_day",
  "maximum_data_age_seconds", "maximum_account_age_seconds"] as const;

function label(value: string) { return value.toLowerCase().replaceAll("_", " "); }

export function LiveControlPanel() {
  const [control, setControl] = useState<LiveControl | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    requestLiveControl().then(value => {
      if (!controller.signal.aborted) { setControl(value); setError(""); }
    }).catch(value => {
      if (!controller.signal.aborted) {
        setError(value instanceof Error ? value.message : "Live control unavailable");
      }
    });
    return () => controller.abort();
  }, []);

  async function configure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!control) return;
    setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const text = (name: string) => String(data.get(name) ?? "").trim();
    const policy: Record<string, string | number> = {
      schema_version: "live-policy-1.0.0", version: text("version"), currency: text("currency"),
      maximum_leverage: text("maximum_leverage"),
    };
    moneyFields.forEach(name => { policy[name] = text(name); });
    fractionFields.forEach(name => { policy[name] = text(name); });
    countFields.forEach(name => { policy[name] = Number(text(name)); });
    try {
      setControl(await requestLiveControl("PUT", {
        expected_revision: control.revision, broker: text("broker"), market: text("market"),
        account_identity_hash: text("account_identity_hash"), policy,
        confirmation: "CONFIGURE LIVE CONTROL",
      }));
    } catch (value) { setError(value instanceof Error ? value.message : "Configuration failed"); }
    finally { setBusy(false); }
  }

  async function transition(action: typeof actions[number]) {
    if (!control) return;
    const expected = action.replaceAll("_", " ");
    if (confirmation !== expected) { setError(`Escreve “${expected}” para confirmar.`); return; }
    setBusy(true); setError("");
    try {
      setControl(await requestLiveControl("POST", {
        expected_revision: control.revision, action, confirmation,
      })); setConfirmation("");
    } catch (value) { setError(value instanceof Error ? value.message : "Transition failed"); }
    finally { setBusy(false); }
  }

  const readiness = control?.readiness;
  const gates = readiness ? Object.entries(readiness).filter(([name]) => name.endsWith("_ready")
    || name.endsWith("_healthy") || name.endsWith("_qualified")) : [];
  return <section className="live-control-page" aria-labelledby="live-control-title">
    <header className="live-control-heading">
      <div><p className="eyebrow">OPERATOR CONTROL PLANE</p><h1 id="live-control-title">Live Trading</h1>
        <p>O backend é autoritativo. Nenhum controlo do browser envia uma ordem.</p></div>
      <strong className={`mode-badge mode-${control?.mode.toLowerCase() ?? "unknown"}`}>
        {control?.mode ?? "UNAVAILABLE"}</strong>
    </header>
    {error && <p className="live-error" role="alert">{error}</p>}
    <div className="live-summary">
      <article><span>Broker</span><strong>{control?.broker ?? "Não configurado"}</strong></article>
      <article><span>Mercado</span><strong>{control?.market ?? "Não configurado"}</strong></article>
      <article><span>Deployment LIVE</span><strong>{control?.live_deployment_enabled ? "ENABLED" : "DISABLED"}</strong></article>
      <article><span>Kill switch</span><strong>{control?.kill_switch_active ? "ACTIVE" : "CLEAR"}</strong></article>
      <article><span>Revisão</span><strong>{control?.revision ?? "—"}</strong></article>
      <article><span>Conta</span><strong>{control?.account_identity_hash ? `${control.account_identity_hash.slice(0, 10)}…` : "Não vinculada"}</strong></article>
    </div>
    <div className="live-grid">
      <form key={control?.revision ?? "loading"} className="control-card policy-form" onSubmit={configure}>
        <h2>Política e conta</h2><p>Todos os limites são definidos pelo operador e validados no backend.</p>
        <div className="form-grid">
          <label>Broker<select name="broker" defaultValue={control?.broker ?? "BINANCE"}><option>BINANCE</option><option>KUCOIN</option></select></label>
          <label>Mercado<select name="market" defaultValue={control?.market ?? "SPOT"}><option>SPOT</option><option>FUTURES</option></select></label>
          <label>Versão<input required name="version" defaultValue={control?.policy?.version ?? ""} /></label>
          <label>Moeda<input required name="currency" pattern="[A-Z0-9]{2,12}" defaultValue={control?.policy?.currency ?? ""} /></label>
          <label className="wide">Hash da conta<input required name="account_identity_hash" pattern="[0-9a-f]{64}" defaultValue={control?.account_identity_hash ?? ""} /></label>
          {moneyFields.map(name => <label key={name}>{label(name)}<input required name={name} inputMode="decimal" defaultValue={control?.policy?.[name] ?? ""} /></label>)}
          <label>maximum leverage<input required name="maximum_leverage" inputMode="decimal" defaultValue={control?.policy?.maximum_leverage ?? ""} /></label>
          {fractionFields.map(name => <label key={name}>{label(name)}<input required name={name} inputMode="decimal" defaultValue={control?.policy?.[name] ?? ""} /></label>)}
          {countFields.map(name => <label key={name}>{label(name)}<input required name={name} type="number" min="1" defaultValue={control?.policy?.[name] ?? ""} /></label>)}
        </div><button disabled={busy || !control} type="submit">Guardar política</button>
      </form>
      <div className="control-stack">
        <section className="control-card"><h2>Readiness</h2>
          {gates.length ? <ul className="gate-list">{gates.map(([name, passed]) => <li key={name}><i className={`status-dot ${passed ? "status-dot-safe" : "status-dot-danger"}`} />{label(name)} <strong>{passed ? "PASS" : "FAIL"}</strong></li>)}</ul>
            : <p className="muted">Sem evidência independente atual. LIVE_ACTIVE permanece bloqueado.</p>}
        </section>
        <section className="control-card"><h2>Ações operacionais</h2>
          <label>Confirmação exata<input value={confirmation} onChange={event => setConfirmation(event.target.value)} placeholder="ARM LIVE" /></label>
          <div className="action-grid">{actions.map(action => <button type="button" disabled={busy || !control} key={action} onClick={() => void transition(action)} className={action.includes("KILL") ? "danger" : ""}>{label(action)}</button>)}</div>
          <small>O kill switch impede novas ordens, persiste após reinício e exige RESET KILL SWITCH antes de novo armamento.</small>
        </section>
      </div>
    </div>
  </section>;
}
