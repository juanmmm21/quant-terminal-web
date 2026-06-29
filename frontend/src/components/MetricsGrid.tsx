import type { PerformanceMetrics } from "../types/api";

interface MetricsGridProps {
  metrics: PerformanceMetrics;
}

function formatPct(value: string): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return value;
  }
  return `${(numeric * 100).toFixed(2)}%`;
}

export function MetricsGrid({ metrics }: MetricsGridProps) {
  const items = [
    { label: "Sharpe", value: metrics.sharpe_ratio },
    { label: "Sortino", value: metrics.sortino_ratio },
    { label: "Profit Factor", value: metrics.profit_factor },
    { label: "Max Drawdown", value: formatPct(metrics.max_drawdown_pct) },
    { label: "Total Return", value: formatPct(metrics.total_return_pct) },
    { label: "Win Rate", value: formatPct(metrics.win_rate) },
    { label: "Trades", value: String(metrics.trade_count) },
    { label: "Symbol", value: metrics.symbol },
  ];

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Performance Metrics</h2>
      </header>
      <div className="metrics-grid">
        {items.map((item) => (
          <div key={item.label} className="metric-card">
            <span className="metric-label">{item.label}</span>
            <span className="metric-value">{item.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
