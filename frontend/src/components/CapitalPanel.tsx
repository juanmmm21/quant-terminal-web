import type { EquityCurve } from "../types/api";
import { formatMoney } from "../utils/format";

interface CapitalPanelProps {
  equity: EquityCurve;
}

export function CapitalPanel({ equity }: CapitalPanelProps) {
  const initial = Number(equity.initial_capital);
  const current = Number(equity.current_capital);
  const delta = current - initial;
  const deltaPct = initial > 0 ? (delta / initial) * 100 : 0;

  return (
    <section className="capital-panel">
      <header className="section-header">
        <div>
          <h2>{equity.label}</h2>
          <p className="section-subtitle">
            Dinero total de tu cuenta en {equity.currency}, no el precio de {equity.symbol}
          </p>
        </div>
      </header>
      <div className="capital-stats">
        <div>
          <span className="stat-label">Inicial</span>
          <strong>{formatMoney(equity.initial_capital)} {equity.currency}</strong>
        </div>
        <div>
          <span className="stat-label">Actual</span>
          <strong>{formatMoney(equity.current_capital)} {equity.currency}</strong>
        </div>
        <div>
          <span className="stat-label">Variación</span>
          <strong className={delta >= 0 ? "price-up" : "price-down"}>
            {delta >= 0 ? "+" : ""}
            {formatMoney(String(delta))} ({deltaPct >= 0 ? "+" : ""}
            {deltaPct.toFixed(2)} %)
          </strong>
        </div>
      </div>
    </section>
  );
}
