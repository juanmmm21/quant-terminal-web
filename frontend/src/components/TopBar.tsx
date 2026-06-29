import type { TerminalSummary } from "../types/api";
import { formatDateTime, formatMoney, formatPercent } from "../utils/format";
import { BotStatusBadge } from "./BotStatusBadge";

interface TopBarProps {
  summary: TerminalSummary;
  apiVersion: string;
  refreshing: boolean;
  onRefresh: () => void;
}

function verdictLabel(verdict: string): string {
  const map: Record<string, string> = {
    buy: "Comprar",
    sell: "Vender",
    hold: "Mantener",
  };
  return map[verdict] ?? verdict;
}

export function TopBar({ summary, apiVersion, refreshing, onRefresh }: TopBarProps) {
  const changeNum = Number(summary.change_pct);

  return (
    <header className="top-bar">
      <div className="brand-block">
        <p className="brand-kicker">quant-core-infra</p>
        <h1>Terminal Quant</h1>
      </div>

      <div className="ticker-strip">
        <div className="ticker-card">
          <span className="ticker-label">Precio {summary.symbol}</span>
          <strong>
            {formatMoney(summary.last_price)} {summary.price_currency}
          </strong>
          <small className={changeNum >= 0 ? "price-up" : "price-down"}>
            {Number.isNaN(changeNum) ? summary.change_pct : formatPercent(summary.change_pct)}
          </small>
        </div>
        <div className="ticker-card highlight-recommendation">
          <span className="ticker-label">Recomendación ({summary.analysis_timeframe})</span>
          <strong className={`verdict-${summary.recommendation_verdict}`}>
            {verdictLabel(summary.recommendation_verdict).toUpperCase()}
          </strong>
          <small>{(summary.recommendation_confidence * 100).toFixed(0)}% confianza</small>
        </div>
        <div className="ticker-card">
          <span className="ticker-label">Motor</span>
          <BotStatusBadge status={summary.bot_status} />
        </div>
      </div>

      <div className="top-actions">
        <span className={`mode-pill mode-${summary.data_mode}`}>
          {summary.data_mode === "live" ? "Live" : "Demo"}
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
