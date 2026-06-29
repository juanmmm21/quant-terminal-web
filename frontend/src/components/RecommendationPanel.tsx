import type { AnalysisSnapshot } from "../types/api";
import { formatDateTime, formatPercent } from "../utils/format";

interface RecommendationPanelProps {
  analysis: AnalysisSnapshot | null;
}

function verdictLabel(verdict: string): string {
  const map: Record<string, string> = {
    buy: "Comprar",
    sell: "Vender",
    hold: "Mantener",
  };
  return map[verdict] ?? verdict;
}

export function RecommendationPanel({ analysis }: RecommendationPanelProps) {
  if (!analysis) {
    return (
      <section className="panel-card">
        <h3>Recomendación</h3>
        <p className="empty-state">Sin análisis todavía. Arranca con <code>python3 scripts/start_terminal.py</code>.</p>
      </section>
    );
  }

  const { recommendation, indicators, training } = analysis;

  return (
    <section className="panel-card recommendation-panel">
      <h3>Recomendación actual</h3>
      <div className={`verdict-card verdict-${recommendation.verdict}`}>
        <span className="verdict-title">{verdictLabel(recommendation.verdict).toUpperCase()}</span>
        <strong className="verdict-confidence">{(recommendation.confidence * 100).toFixed(0)}% confianza</strong>
        <p>{recommendation.reason}</p>
        <dl className="indicator-grid">
          <div>
            <dt>RSI</dt>
            <dd>{indicators.rsi?.toFixed(1) ?? "—"}</dd>
          </div>
          <div>
            <dt>MACD</dt>
            <dd>{indicators.macd_line?.toFixed(2) ?? "—"}</dd>
          </div>
          <div>
            <dt>Señal MACD</dt>
            <dd>{indicators.signal_line?.toFixed(2) ?? "—"}</dd>
          </div>
          <div>
            <dt>Precio ref.</dt>
            <dd>{recommendation.reference_price}</dd>
          </div>
        </dl>
      </div>

      <div className="training-block">
        <h4>Entrenamiento histórico</h4>
        <ul className="training-stats">
          <li>
            <span>Barras analizadas</span>
            <strong>{training.bars_analyzed}</strong>
          </li>
          <li>
            <span>Señales históricas</span>
            <strong>{training.signal_count}</strong>
          </li>
          <li>
            <span>Acierto direccional</span>
            <strong>{formatPercent(training.directional_win_rate)}</strong>
          </li>
          <li>
            <span>Estrategia seleccionada</span>
            <strong>{training.selected_strategy}</strong>
          </li>
        </ul>
        <p className="training-updated">Actualizado {formatDateTime(analysis.updated_at)}</p>
      </div>
    </section>
  );
}
