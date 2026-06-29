import type { SignalMarker } from "../types/api";
import { formatDateTime, formatMoney } from "../utils/format";

interface SignalHistoryProps {
  signals: SignalMarker[];
}

export function SignalHistory({ signals }: SignalHistoryProps) {
  if (signals.length === 0) {
    return (
      <section className="panel-card">
        <h3>Historial de señales</h3>
        <p className="empty-state">Aún no hay señales en este marco temporal.</p>
      </section>
    );
  }

  const recent = [...signals].sort(
    (a, b) => new Date(b.event_time).getTime() - new Date(a.event_time).getTime(),
  );

  return (
    <section className="panel-card signal-history">
      <h3>Historial de señales</h3>
      <ul className="signal-list">
        {recent.slice(0, 12).map((signal) => (
          <li key={`${signal.event_time}-${signal.action}`} className={`signal-item action-${signal.action}`}>
            <div className="signal-head">
              <strong>{signal.action === "enter" ? "Entrada larga" : signal.action === "exit" ? "Salida" : signal.action}</strong>
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
    </section>
  );
}
