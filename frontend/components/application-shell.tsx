"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LiveModeIndicator } from "./live-mode-indicator";

const navigation = [
  ["Dashboard", "/", "⌂"],
  ["Analyze", "/#analysis", "◫"],
  ["Watchlists", "/#watchlists", "≋"],
  ["Scanner", "/#scanner", "⌕"],
  ["Portfolio", "/#portfolio", "▣"],
  ["Strategies", "/capabilities/strategies", "⌘"],
  ["Backtesting", "/capabilities/backtesting", "⌁"],
  ["Research Factory", "/capabilities/research", "♙"],
  ["Market Intelligence", "/#market-intelligence", "◴"],
  ["Execution", "/capabilities/execution", "↗"],
  ["Live Trading", "/live-trading", "●"],
  ["Risk", "/capabilities/risk", "♢"],
  ["Paper Trading", "/paper", "◎"],
  ["System Health", "/system", "◇"],
] as const;

export function ApplicationShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return <div className="terminal-shell">
    <a className="skip-link" href="#main-content">Saltar para o conteúdo</a>
    <aside className="primary-sidebar" aria-label="Navegação principal">
      <Link className="terminal-brand" href="/" aria-label="Pocket Alpha — início">
        <span className="terminal-logo" aria-hidden="true"><i />▲</span><strong>Pocket Alpha</strong>
      </Link>
      <nav className="primary-nav" aria-label="Navegação principal">
        {navigation.map(([label, href, icon]) => <Link key={label} href={href}
          aria-current={(href === "/" ? pathname === "/" : pathname === href) ? "page" : undefined}>
          <span aria-hidden="true">{icon}</span>{label}
        </Link>)}
      </nav>
      <div className="system-rail" aria-label="Estado esperado do sistema">
        <small>SYSTEM</small>
        <span><i className="status-dot status-dot-neutral" />Data status via API</span>
        <span><i className="status-dot status-dot-neutral" />Dependencies checked</span>
        <span><i className="status-dot status-dot-neutral" />Control state via API</span>
        <b>v0.3.0</b>
      </div>
    </aside>
    <div className="terminal-stage">
      <header className="terminal-topbar">
        <Link className="global-search" href="/#search"><span aria-hidden="true">⌕</span>Search assets (BTC, ETH, AAPL, …)</Link>
        <div className="market-feed" aria-label="Origem da informação de mercado">
          <span><i className="status-dot status-dot-neutral" /> Stored market observations</span>
          <span>UTC</span>
        </div>
        <LiveModeIndicator />
        <div className="operator-avatar" aria-label="Operador autenticado">PA</div>
      </header>
      <main id="main-content" className="terminal-content">{children}</main>
    </div>
  </div>;
}
