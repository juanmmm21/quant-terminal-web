import type { AnalysisSnapshot } from "../types/api";
import { GLOSSARY } from "../utils/glossary";
import { confidenceLabel, humanizeVerdict } from "../utils/humanize";
import { formatDateTime, formatPercent } from "../utils/format";
import { HelpTip } from "./HelpTip";

interface RecommendationPanelProps {
  analysis: AnalysisSnapshot | null;
}

export function RecommendationPanel({ analysis }: RecommendationPanelProps) {
  if (!analysis) {
    return null;
  }

  const { recommendation, indicators, training } = analysis;
  const verdict = humanizeVerdict(recommendation.verdict);

  return (
    <section className="panel-card recommendation-panel">
      <div className="panel-title-row">
        <h3>Recomendación</h3>
        <HelpTip text={GLOSSARY.recommendation.description} />
      </div>

      <div className={`verdict-card verdict-${recommendation.verdict}`}>
        <span className="verdict-title">{verdict.label.toUpperCase()}</span>
        <strong className="verdict-confidence">
          {(recommendation.confidence * 100).toFixed(0)}%
        </strong>
        <p className="confidence-explainer">{confidenceLabel(recommendation.confidence)}</p>
        <p className="verdict-reason">{recommendation.reason}</p>

        <div className="indicator-section">
          <div className="indicator-section-head">
            <h4>Indicadores</h4>
          </div>
          <dl className="indicator-grid">
            <div>
              <dt>
                RSI <HelpTip text={GLOSSARY.rsi.description} label="RSI" />
              </dt>
              <dd>{indicators.rsi?.toFixed(1) ?? "—"}</dd>
            </div>
            <div>
              <dt>
                MACD <HelpTip text={GLOSSARY.macd.description} label="MACD" />
              </dt>
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
      </div>

      <div className="training-block">
        <div className="panel-title-row">
          <h4>Histórico</h4>
          <HelpTip text={GLOSSARY.training.description} />
        </div>
        <ul className="training-stats">
          <li>
            <span>Velas</span>
            <strong>{training.bars_analyzed}</strong>
          </li>
          <li>
            <span>Señales</span>
            <strong>{training.signal_count}</strong>
          </li>
          <li>
            <span>Acierto</span>
            <strong>{formatPercent(training.directional_win_rate)}</strong>
          </li>
          <li>
            <span>Estrategia</span>
            <strong>{training.selected_strategy}</strong>
          </li>
        </ul>
        <p className="training-updated">{formatDateTime(analysis.updated_at)}</p>
      </div>
    </section>
  );
}
