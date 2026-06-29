import type { PerformanceMetrics } from "../types/api";

interface MetricsGridProps {
  metrics: PerformanceMetrics;
}

function formatPct(value: string): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return value;
  }
  return `${(numeric * 100).toFixed(2)} %`;
}

export function MetricsGrid({ metrics }: MetricsGridProps) {
  const items = [
    { label: "Sharpe", value: metrics.sharpe_ratio, hint: "Riesgo ajustado" },
    { label: "Sortino", value: metrics.sortino_ratio, hint: "Solo volatilidad bajista" },
    { label: "Profit factor", value: metrics.profit_factor, hint: "Ganancias / pérdidas" },
    { label: "Drawdown máx.", value: formatPct(metrics.max_drawdown_pct), hint: "Peor caída" },
    { label: "Retorno total", value: formatPct(metrics.total_return_pct), hint: "Sobre el periodo" },
    { label: "Win rate", value: formatPct(metrics.win_rate), hint: "Operaciones ganadoras" },
    { label: "Operaciones", value: String(metrics.trade_count), hint: "Round-trips cerrados" },
    { label: "Símbolo", value: metrics.symbol, hint: "Activo evaluado" },
  ];

  return (
    <section className="panel">
      <header className="section-header">
        <h2>Métricas de rendimiento</h2>
        <p className="section-subtitle">{metrics.trade_count} round-trips evaluados</p>
      </header>
      <div className="metrics-grid">
        {items.map((item) => (
          <div key={item.label} className="metric-card" title={item.hint}>
            <span className="metric-label">{item.label}</span>
            <span className="metric-value">{item.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
