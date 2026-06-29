import { useLayoutEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";

import type { AnalysisSnapshot, Candle, Timeframe } from "../types/api";
import { prepareChartCandles, toChartTime } from "../utils/chartData";
import { GLOSSARY } from "../utils/glossary";
import { humanizeVerdict } from "../utils/humanize";
import { formatDateTime, formatMoney } from "../utils/format";
import { HelpTip } from "./HelpTip";

export const TIMEFRAMES: Timeframe[] = ["1m", "5m", "10m", "15m", "1h"];

const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  "1m": "1 min",
  "5m": "5 min",
  "10m": "10 min",
  "15m": "15 min",
  "1h": "1 hora",
};

interface TradingChartProps {
  symbol: string;
  currency: string;
  timeframe: Timeframe;
  lastPrice: string;
  changePct: string;
  candles: Candle[];
  analysis: AnalysisSnapshot | null;
  loading?: boolean;
  onTimeframeChange: (timeframe: Timeframe) => void;
}

function applySeriesData(
  candleSeries: ISeriesApi<"Candlestick">,
  volumeSeries: ISeriesApi<"Histogram">,
  chart: IChartApi,
  candles: Candle[],
  analysis: AnalysisSnapshot | null,
  previousBarCount: number,
): number {
  const bars = prepareChartCandles(candles);
  if (bars.length === 0) {
    return 0;
  }

  const canIncremental =
    previousBarCount > 0 &&
    bars.length >= previousBarCount &&
    bars.length - previousBarCount <= 2;

  if (canIncremental && bars.length === previousBarCount) {
    const last = bars[bars.length - 1];
    candleSeries.update({
      time: last.time,
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
    });
    volumeSeries.update({
      time: last.time,
      value: last.volume,
      color: last.close >= last.open ? "rgba(34, 197, 94, 0.35)" : "rgba(239, 68, 68, 0.35)",
    });
  } else if (canIncremental && bars.length === previousBarCount + 1) {
    const last = bars[bars.length - 1];
    candleSeries.update({
      time: last.time,
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
    });
    volumeSeries.update({
      time: last.time,
      value: last.volume,
      color: last.close >= last.open ? "rgba(34, 197, 94, 0.35)" : "rgba(239, 68, 68, 0.35)",
    });
  } else {
    candleSeries.setData(
      bars.map((bar) => ({
        time: bar.time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );
    volumeSeries.setData(
      bars.map((bar) => {
        const up = bar.close >= bar.open;
        return {
          time: bar.time,
          value: bar.volume,
          color: up ? "rgba(34, 197, 94, 0.35)" : "rgba(239, 68, 68, 0.35)",
        };
      }),
    );
    chart.timeScale().fitContent();
  }

  const candleTimes = new Set(bars.map((bar) => bar.time));
  const markers: SeriesMarker<Time>[] = [];
  for (const signal of analysis?.signals ?? []) {
    const time = toChartTime(signal.event_time);
    if (!candleTimes.has(time)) {
      continue;
    }
    const isBuy = signal.action === "enter";
    markers.push({
      time,
      position: isBuy ? "belowBar" : "aboveBar",
      color: isBuy ? "#22c55e" : "#ef4444",
      shape: isBuy ? "arrowUp" : "arrowDown",
      text: isBuy ? "COMPRA" : "VENTA",
    });
  }

  try {
    candleSeries.setMarkers(markers);
  } catch {
    candleSeries.setMarkers([]);
  }

  return bars.length;
}

export function TradingChart({
  symbol,
  currency,
  timeframe,
  lastPrice,
  changePct,
  candles,
  analysis,
  loading = false,
  onTimeframeChange,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const barCountRef = useRef(0);
  const [chartReady, setChartReady] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const width = container.clientWidth > 0 ? container.clientWidth : 640;
    const height = container.clientHeight > 0 ? container.clientHeight : 460;

    const chart = createChart(container, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#0f1419" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.08)" },
        horzLines: { color: "rgba(148, 163, 184, 0.08)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.2)" },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.2)",
        timeVisible: true,
        secondsVisible: timeframe === "1m",
      },
      handleScroll: { vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    setChartReady(true);

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const nextWidth = entry.contentRect.width;
        const nextHeight = entry.contentRect.height;
        if (nextWidth > 0 && nextHeight > 0) {
          chart.applyOptions({ width: nextWidth, height: nextHeight });
        }
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      setChartReady(false);
      barCountRef.current = 0;
    };
  }, []);

  useLayoutEffect(() => {
    if (!chartReady) {
      return;
    }
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const chart = chartRef.current;
    if (!candleSeries || !volumeSeries || !chart) {
      return;
    }
    barCountRef.current = applySeriesData(
      candleSeries,
      volumeSeries,
      chart,
      candles,
      analysis,
      barCountRef.current,
    );
  }, [chartReady, candles, analysis]);

  useLayoutEffect(() => {
    barCountRef.current = 0;
  }, [timeframe]);

  useLayoutEffect(() => {
    chartRef.current?.timeScale().applyOptions({
      secondsVisible: timeframe === "1m",
    });
  }, [timeframe]);

  const toggleFullscreen = async () => {
    const node = containerRef.current?.closest(".trading-chart-panel");
    if (!node) {
      return;
    }
    if (!document.fullscreenElement) {
      await node.requestFullscreen();
      setFullscreen(true);
    } else {
      await document.exitFullscreen();
      setFullscreen(false);
    }
  };

  const changeNum = Number(changePct);
  const changeLabel = Number.isNaN(changeNum)
    ? changePct
    : `${changeNum >= 0 ? "+" : ""}${(changeNum * 100).toFixed(2)} %`;

  const recommendation = analysis?.recommendation;
  const verdict = recommendation ? humanizeVerdict(recommendation.verdict) : null;
  const bars = prepareChartCandles(candles);

  return (
    <section className={`chart-panel trading-chart-panel ${fullscreen ? "is-fullscreen" : ""}`}>
      <header className="chart-header">
        <div>
          <div className="chart-title-row">
            <h2>{symbol}</h2>
            <HelpTip text={GLOSSARY.timeframe.description} label="Marco temporal" />
          </div>
          <p className="chart-subtitle">
            {TIMEFRAME_LABELS[timeframe]} · {bars.length} velas · {currency}
          </p>
        </div>
        <div className="chart-price-block">
          <span className="chart-last-price">
            {formatMoney(lastPrice)} {currency}
          </span>
          <span className={changeNum >= 0 ? "price-up" : "price-down"}>
            {changeLabel}
            <HelpTip text={GLOSSARY.changePct.description} label="Variación" />
          </span>
          {recommendation && verdict ? (
            <span className={`verdict-pill verdict-${recommendation.verdict}`}>
              {verdict.label.toUpperCase()} · {(recommendation.confidence * 100).toFixed(0)}%
            </span>
          ) : null}
        </div>
      </header>

      <div className="chart-toolbar">
        <div className="timeframe-tabs" role="tablist" aria-label="Marco temporal">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              type="button"
              role="tab"
              aria-selected={timeframe === tf}
              className={timeframe === tf ? "tf-tab active" : "tf-tab"}
              onClick={() => onTimeframeChange(tf)}
              disabled={loading}
            >
              {tf}
            </button>
          ))}
        </div>
        <div className="chart-toolbar-actions">
          <button
            type="button"
            className="btn-ghost btn-sm"
            onClick={() => chartRef.current?.timeScale().fitContent()}
          >
            Ajustar zoom
          </button>
          <button type="button" className="btn-ghost btn-sm" onClick={() => void toggleFullscreen()}>
            {fullscreen ? "Salir pantalla completa" : "Pantalla completa"}
          </button>
        </div>
      </div>

      <div
        className="chart-canvas-wrap"
        ref={containerRef}
        style={{ height: fullscreen ? "calc(100vh - 140px)" : 460, minHeight: 460 }}
      />

      {recommendation && verdict ? (
        <div className="recommendation-hint">
          <strong>{verdict.label}</strong>
          <span>{recommendation.reason}</span>
          {recommendation.event_time ? (
            <span className="hint-meta">{formatDateTime(recommendation.event_time)}</span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
