import type { TerminalSummary } from "../types/api";
import { formatDateTime, formatMoney } from "../utils/format";
import { BotStatusBadge } from "./BotStatusBadge";

interface TopBarProps {
  summary: TerminalSummary;
  apiVersion: string;
  refreshing: boolean;
  onRefresh: () => void;
}

export function TopBar({ summary, apiVersion, refreshing, onRefresh }: TopBarProps) {
  const capitalChange = Number(summary.capital_change);
  const changeClass = capitalChange >= 0 ? "price-up" : "price-down";

  return (
    <header className="top-bar">
      <div className="brand-block">
        <p className="brand-kicker">quant-core-infra</p>
        <h1>Terminal Quant</h1>
      </div>

      <div className="ticker-strip">
        <div className="ticker-card">
          <span className="ticker-label">Precio BTC</span>
          <strong>{formatMoney(summary.last_price)} {summary.price_currency}</strong>
        </div>
        <div className="ticker-card highlight-capital">
          <span className="ticker-label">Capital cuenta</span>
          <strong>{formatMoney(summary.account_capital)} {summary.capital_currency}</strong>
          <small className={changeClass}>
            {capitalChange >= 0 ? "+" : ""}
            {formatMoney(summary.capital_change)} vs inicio
          </small>
        </div>
        <div className="ticker-card">
          <span className="ticker-label">Round-trips</span>
          <strong>{summary.trade_count}</strong>
        </div>
        <div className="ticker-card">
          <span className="ticker-label">Estado bot</span>
          <BotStatusBadge status={summary.bot_status} />
        </div>
      </div>

      <div className="top-actions">
        <span className={`mode-pill mode-${summary.data_mode}`}>
          {summary.data_mode === "live" ? "Datos live" : "Modo demo"}
        </span>
        <span className="sync-label">Sync {formatDateTime(summary.last_sync)}</span>
        <span className="api-label">v{apiVersion}</span>
        <button type="button" className="btn-ghost" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Actualizando…" : "Actualizar"}
        </button>
      </div>
    </header>
  );
}
