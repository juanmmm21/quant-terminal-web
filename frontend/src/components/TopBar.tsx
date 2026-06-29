import type { TerminalSummary } from "../types/api";
import { GLOSSARY } from "../utils/glossary";
import { confidenceLabel, humanizeVerdict } from "../utils/humanize";
import { formatDateTime, formatMoney, formatPercent } from "../utils/format";
import { BotStatusBadge } from "./BotStatusBadge";
import { HelpTip } from "./HelpTip";

interface TopBarProps {
  summary: TerminalSummary;
  apiVersion: string;
  refreshing: boolean;
  onRefresh: () => void;
}

export function TopBar({ summary, apiVersion, refreshing, onRefresh }: TopBarProps) {
  const changeNum = Number(summary.change_pct);
  const verdict = humanizeVerdict(summary.recommendation_verdict);

  return (
    <header className="top-bar">
      <div className="brand-block">
        <p className="brand-kicker">Asistente de trading</p>
        <h1>Terminal Quant</h1>
        <p className="brand-tagline">Recomendaciones claras sobre Bitcoin en tiempo real</p>
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
          <span className="ticker-label">
            Recomendación ({summary.analysis_timeframe})
            <HelpTip text={GLOSSARY.recommendation.description} />
          </span>
          <strong className={`verdict-${summary.recommendation_verdict}`}>
            {verdict.label.toUpperCase()}
          </strong>
          <small>
            {(summary.recommendation_confidence * 100).toFixed(0)}% ·{" "}
            {confidenceLabel(summary.recommendation_confidence)}
          </small>
        </div>
        <div className="ticker-card">
          <span className="ticker-label">Motor</span>
          <BotStatusBadge status={summary.bot_status} />
        </div>
      </div>

      <div className="top-actions">
        <span className={`mode-pill mode-${summary.data_mode}`}>
          {summary.data_mode === "live" ? "En vivo" : "Demo"}
        </span>
        <span className="sync-label">Actualizado {formatDateTime(summary.last_sync)}</span>
        <span className="api-label">v{apiVersion}</span>
        <button type="button" className="btn-ghost" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Actualizando…" : "Actualizar datos"}
        </button>
      </div>
    </header>
  );
}
