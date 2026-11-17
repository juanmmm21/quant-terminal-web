import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ColorType, createChart, type UTCTimestamp } from "lightweight-charts";

import type { PublicPaperComparison } from "../types/api";
import { formatDateTime } from "../utils/format";

const REFRESH_MS = 60_000;

function toSeries(points: { at: string; equity: string }[]) {
  const seen = new Set<number>();
  const rows: { time: UTCTimestamp; value: number }[] = [];
  for (const point of points) {
    const time = Math.floor(new Date(point.at).getTime() / 1000);
    if (!Number.isFinite(time) || seen.has(time)) {
      continue;
    }
    seen.add(time);
    rows.push({ time: time as UTCTimestamp, value: Number(point.equity) });
  }
  return rows.sort((a, b) => a.time - b.time);
}

function pct(value: number | undefined | null): string {
  return value === undefined || value === null ? "—" : `${(value * 100).toFixed(2)}%`;
}

function EquityChart({ data }: { data: PublicPaperComparison }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    const container = ref.current;
    if (!container) {
      return;
    }
    const chart = createChart(container, {
      height: 320,
      layout: { background: { type: ColorType.Solid, color: "#0f1419" }, textColor: "#cbd5e1" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      timeScale: { timeVisible: true },
    });
    const paper = chart.addLineSeries({ color: "#2dd4bf", lineWidth: 2, title: "Paper (testnet)" });
    paper.setData(toSeries(data.paper.equity_curve));
    if (data.backtest) {
      const backtest = chart.addLineSeries({ color: "#f59e0b", lineWidth: 2, title: "Backtest" });
      backtest.setData(toSeries(data.backtest.equity_curve));
    }
    chart.timeScale().fitContent();
    const resize = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }));
    resize.observe(container);
    return () => {
      resize.disconnect();
      chart.remove();
    };
  }, [data]);
  return <div ref={ref} className="public-chart" aria-label="Equity: paper vs backtest" />;
}

export function PublicPaperView() {
  const [data, setData] = useState<PublicPaperComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch("/api/v1/public/paper");
        if (!response.ok) {
          throw new Error(response.status === 404 ? "El paper trading aún no ha empezado." : `HTTP ${response.status}`);
        }
        const body = (await response.json()) as PublicPaperComparison;
        if (!cancelled) {
          setData(body);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "No disponible");
        }
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="app-shell public-shell">
      <header className="panel-card">
        <p className="brand-kicker">Quant · vista pública de solo lectura</p>
        <h1>Paper trading vs. backtest</h1>
        {data ? (
          <p className="validation-meta">
            <strong>{data.strategy}</strong> · {data.timeframe} · {data.symbol} · {data.venue} ·{" "}
            {formatDateTime(data.period_start)} → {formatDateTime(data.period_end)} ·{" "}
            {data.trader_alive ? "proceso activo" : "proceso sin latido"}
          </p>
        ) : null}
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      {data ? (
        <>
          <section className="panel-card">
            <EquityChart data={data} />
            <table className="public-table">
              <thead>
                <tr>
                  <th />
                  <th>Paper (testnet)</th>
                  <th>Backtest (mismo periodo)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>P&amp;L (USDT)</th>
                  <td>{Number(data.paper.pnl).toFixed(2)}</td>
                  <td>{data.backtest ? Number(data.backtest.pnl).toFixed(2) : "—"}</td>
                </tr>
                <tr>
                  <th>Rentabilidad</th>
                  <td>{pct(data.paper.return_pct)}</td>
                  <td>{pct(data.backtest?.return_pct)}</td>
                </tr>
                <tr>
                  <th>Ejecuciones</th>
                  <td>{data.paper.fills}</td>
                  <td>{data.backtest?.fills ?? "—"}</td>
                </tr>
              </tbody>
            </table>
            {data.backtest_error ? <p className="validation-note">Backtest: {data.backtest_error}</p> : null}
            <p className="validation-note">
              Validación previa: DSR {data.validation.deflated_sharpe_ratio ?? "—"} · PBO{" "}
              {data.validation.pbo ?? "—"} ·{" "}
              {data.gate_passed ? "superó la validación" : "promovida SIN superar la validación"}
            </p>
            <p className="validation-note">{data.disclaimer}</p>
            <p className="validation-note">Actualizado {formatDateTime(data.generated_at)}</p>
          </section>
        </>
      ) : null}
    </div>
  );
}
