import type { SignalMarker } from "../types/api";
import { GLOSSARY } from "../utils/glossary";
import { formatDateTime, formatMoney } from "../utils/format";
import { HelpTip } from "./HelpTip";

interface SignalHistoryProps {
  signals: SignalMarker[];
}

function actionLabel(action: string): string {
  if (action === "enter") {
    return "Entrada";
  }
  if (action === "exit") {
    return "Salida";
  }
  return action;
}

export function SignalHistory({ signals }: SignalHistoryProps) {
  const recent = [...signals].sort(
    (a, b) => new Date(b.event_time).getTime() - new Date(a.event_time).getTime(),
  );

  return (
    <section className="panel-card signal-history">
      <div className="panel-title-row">
        <h3>Historial de señales</h3>
        <HelpTip text={GLOSSARY.signals.description} />
      </div>
      {recent.length === 0 ? (
        <ul className="signal-list signal-list--empty" aria-label="Sin señales" />
      ) : (
        <ul className="signal-list">
          {recent.slice(0, 12).map((signal) => (
            <li
              key={`${signal.event_time}-${signal.action}-${signal.strategy_id}`}
              className={`signal-item action-${signal.action}`}
            >
              <div className="signal-head">
                <strong>{actionLabel(signal.action)}</strong>
                <span>{formatDateTime(signal.event_time)}</span>
              </div>
              <p>{signal.reason}</p>
              <div className="signal-meta">
                <span>{formatMoney(signal.reference_price)} USDT</span>
                <span>{(signal.confidence * 100).toFixed(0)}%</span>
                <span>{signal.strategy_id}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
