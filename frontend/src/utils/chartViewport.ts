import type { IChartApi } from "lightweight-charts";

import type { Timeframe } from "../types/api";

/** Velas visibles al cargar o al pulsar «Ajustar zoom». */
export const DEFAULT_VISIBLE_BARS: Record<Timeframe, number> = {
  "1m": 180,
  "5m": 144,
  "10m": 120,
  "15m": 96,
  "1h": 120,
};

export const MAX_CHART_MARKERS = 12;

export function applyDefaultViewport(
  chart: IChartApi,
  barCount: number,
  timeframe: Timeframe,
): void {
  if (barCount <= 0) {
    return;
  }
  const visible = DEFAULT_VISIBLE_BARS[timeframe];
  if (barCount <= visible) {
    chart.timeScale().fitContent();
    return;
  }
  const from = barCount - visible;
  chart.timeScale().setVisibleLogicalRange({ from, to: barCount });
}
