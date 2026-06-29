import type { UTCTimestamp } from "lightweight-charts";

import type { Candle } from "../types/api";

export interface ChartCandleBar {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function toChartTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

/**
 * lightweight-charts exige timestamps únicos y ordenados.
 * El lakehouse puede devolver filas duplicadas o zonas horarias mezcladas.
 */
export function prepareChartCandles(candles: Candle[]): ChartCandleBar[] {
  const byTime = new Map<number, ChartCandleBar>();

  for (const candle of candles) {
    const time = toChartTime(candle.open_time);
    const open = Number(candle.open);
    const high = Number(candle.high);
    const low = Number(candle.low);
    const close = Number(candle.close);
    const volume = Number(candle.volume);

    if ([open, high, low, close, volume].some((value) => Number.isNaN(value))) {
      continue;
    }

    const existing = byTime.get(time);
    if (existing) {
      byTime.set(time, {
        time,
        open: existing.open,
        high: Math.max(existing.high, high),
        low: Math.min(existing.low, low),
        close,
        volume: existing.volume + volume,
      });
    } else {
      byTime.set(time, { time, open, high, low, close, volume });
    }
  }

  return Array.from(byTime.values()).sort((left, right) => left.time - right.time);
}
