import type { GateCheck, Promotion, ValidationResponse } from "../types/api";
import { formatDateTime } from "../utils/format";
import { HelpTip } from "./HelpTip";

const CHECK_LABELS: Record<string, string> = {
  deflated_sharpe_ratio: "Sharpe deflactado (DSR)",
  pbo: "Prob. de sobreajuste (PBO)",
  walk_forward_oos_sharpe: "Sharpe OOS walk-forward",
  purged_kfold_oos_sharpe: "Sharpe OOS k-fold purgado",
  report_age_hours: "Antigüedad del informe (h)",
};

function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(digits);
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(2)}%`;
}

function CheckRow({ check }: { check: GateCheck }) {
  const digits = check.name === "pbo" || check.name === "deflated_sharpe_ratio" ? 3 : 2;
  return (
    <li className={check.passed ? "gate-ok" : "gate-fail"} title={check.explanation}>
      <span>{CHECK_LABELS[check.name] ?? check.name}</span>
      <strong>
        {fmt(check.value, digits)} <small>{check.comparison} {fmt(check.threshold, digits)}</small>
      </strong>
      <span aria-label={check.passed ? "supera" : "no supera"}>{check.passed ? "✓" : "✗"}</span>
    </li>
  );
}

interface ValidationPanelProps {
  validation: ValidationResponse | null;
  validationError: string | null;
  promotion: Promotion | null;
  loading: boolean;
  onRequestPromote: () => void;
  onDemote: () => void;
}

export function ValidationPanel({
  validation,
  validationError,
  promotion,
  loading,
  onRequestPromote,
  onDemote,
}: ValidationPanelProps) {
  const report = validation?.report;
  const gate = validation?.gate;
  const blocked = gate ? !gate.passed && gate.mode === "enforce" : true;

  return (
    <section className="panel-card validation-panel">
      <div className="panel-title-row">
        <h3>Validación fuera de muestra</h3>
        <HelpTip text="Antes de pasar a paper trading, la estrategia elegida se evalúa con walk-forward y validación cruzada purgada con embargo. El Sharpe deflactado descuenta cuántas configuraciones se probaron; el PBO estima la probabilidad de que la ganadora en muestra sea peor que la mediana fuera de muestra." />
      </div>

      {validationError ? <p className="status-message">{validationError}</p> : null}

      {report && gate ? (
        <>
          <p className="validation-meta">
            <strong>{report.strategy}</strong> · {report.timeframe} · {report.n_bars} barras ·{" "}
            {report.n_trials} configuraciones probadas
            <br />
            {report.period_start ? formatDateTime(report.period_start) : "—"} →{" "}
            {report.period_end ? formatDateTime(report.period_end) : "—"}
          </p>
          <dl className="indicator-grid">
            <div>
              <dt>Sharpe anual.</dt>
              <dd>{fmt(report.sharpe_annualized)}</dd>
            </div>
            <div>
              <dt>PSR</dt>
              <dd>{fmt(report.probabilistic_sharpe_ratio, 3)}</dd>
            </div>
            <div>
              <dt>Retorno OOS WF</dt>
              <dd>{pct(report.walk_forward.oos_total_return)}</dd>
            </div>
            <div>
              <dt>Retorno OOS CV</dt>
              <dd>{pct(report.purged_kfold.oos_total_return)}</dd>
            </div>
          </dl>
          <ul className="gate-checks">
            {gate.checks.map((check) => (
              <CheckRow key={check.name} check={check} />
            ))}
          </ul>
          {report.excluded_candidates.length > 0 ? (
            <p className="validation-note">
              Excluidas por no operar: {report.excluded_candidates.join(", ")}
            </p>
          ) : null}
          <p className="validation-note">{report.disclaimer}</p>
        </>
      ) : null}

      {promotion ? (
        <div className={`promotion-box ${promotion.gate_passed ? "" : "promotion-flagged"}`}>
          <p>
            En paper trading: <strong>{promotion.strategy}</strong> ({promotion.timeframe})
            {promotion.gate_passed ? "" : " — promovida sin superar la validación"}
          </p>
          <button type="button" onClick={onDemote} disabled={loading}>
            Retirar de paper
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="button-primary"
          onClick={onRequestPromote}
          disabled={loading || !report || blocked}
          title={blocked ? "La estrategia no supera la validación" : undefined}
        >
          Pasar a paper trading
        </button>
      )}
      {!promotion && blocked && report ? (
        <p className="validation-note">
          Bloqueado: la estrategia no supera la validación (modo {gate?.mode}).
        </p>
      ) : null}
    </section>
  );
}
