import type { EquityPoint } from "../types/api";

interface EquityChartProps {
  symbol: string;
  points: EquityPoint[];
}

function buildPath(points: EquityPoint[], width: number, height: number): string {
  if (points.length === 0) {
    return "";
  }
  const equities = points.map((point) => Number(point.equity));
  const min = Math.min(...equities);
  const max = Math.max(...equities);
  const range = max - min || 1;
  const xStep = points.length > 1 ? width / (points.length - 1) : 0;

  return points
    .map((point, index) => {
      const x = index * xStep;
      const y = height - ((Number(point.equity) - min) / range) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function EquityChart({ symbol, points }: EquityChartProps) {
  const width = 640;
  const height = 220;
  const path = buildPath(points, width, height);
  const latest = points.at(-1)?.equity ?? "—";
  const first = points.at(0)?.equity ?? "—";

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Equity Curve — {symbol}</h2>
        <span className="equity-range">
          {first} → {latest}
        </span>
      </header>
      <svg className="equity-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Equity curve chart">
        <rect x="0" y="0" width={width} height={height} className="chart-bg" />
        {path ? <path d={path} className="equity-line" fill="none" /> : null}
      </svg>
    </section>
  );
}
