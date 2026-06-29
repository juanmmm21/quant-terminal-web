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
import { prepareChartCandles, toChartTime, type ChartCandleBar } from "../utils/chartData";
import {
  applyDefaultViewport,
  DEFAULT_VISIBLE_BARS,
  MAX_CHART_MARKERS,
} from "../utils/chartViewport";
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

function buildChartMarkers(
  signals: AnalysisSnapshot["signals"] | undefined,
  bars: ChartCandleBar[],
  timeframe: Timeframe,
): SeriesMarker<Time>[] {
  const visibleCount = Math.min(bars.length, DEFAULT_VISIBLE_BARS[timeframe]);
  const visibleTimes = new Set(bars.slice(-visibleCount).map((bar) => bar.time));

  const matched = (signals ?? [])
    .map((signal) => ({ signal, time: toChartTime(signal.event_time) }))
    .filter(({ time }) => visibleTimes.has(time))
    .sort((left, right) => right.time - left.time)
    .slice(0, MAX_CHART_MARKERS)
    .sort((left, right) => left.time - right.time);

  return matched.map(({ signal, time }) => {
    const isBuy = signal.action === "enter";
    return {
      time,
      position: isBuy ? "belowBar" : "aboveBar",
      color: isBuy ? "#22c55e" : "#ef4444",
      shape: isBuy ? "arrowUp" : "arrowDown",
    };
  });
}

function applySeriesData(
  candleSeries: ISeriesApi<"Candlestick">,
  volumeSeries: ISeriesApi<"Histogram">,
  candles: Candle[],
  analysis: AnalysisSnapshot | null,
  timeframe: Timeframe,
  previousBarCount: number,
): { count: number; reloaded: boolean } {
  const bars = prepareChartCandles(candles);
  if (bars.length === 0) {
    return { count: 0, reloaded: false };
  }

  const canIncremental =
    previousBarCount > 0 &&
    bars.length >= previousBarCount &&
    bars.length - previousBarCount <= 2;

  let reloaded = false;

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
    reloaded = true;
  }

  const markers = buildChartMarkers(analysis?.signals, bars, timeframe);

  try {
    candleSeries.setMarkers(markers);
  } catch {
    candleSeries.setMarkers([]);
  }

  return { count: bars.length, reloaded };
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
  const userAdjustedViewportRef = useRef(false);
  const suppressViewportTrackingRef = useRef(false);
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
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.2)",
        scaleMargins: { top: 0.08, bottom: 0.22 },
      },
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
      scaleMargins: { top: 0.78, bottom: 0 },
    });

    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      if (suppressViewportTrackingRef.current) {
        suppressViewportTrackingRef.current = false;
        return;
      }
      userAdjustedViewportRef.current = true;
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
      userAdjustedViewportRef.current = false;
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
    const { count, reloaded } = applySeriesData(
      candleSeries,
      volumeSeries,
      candles,
      analysis,
      timeframe,
      barCountRef.current,
    );
    barCountRef.current = count;
    if (reloaded && !userAdjustedViewportRef.current) {
      suppressViewportTrackingRef.current = true;
      applyDefaultViewport(chart, count, timeframe);
    }
  }, [chartReady, candles, analysis, timeframe]);

  useLayoutEffect(() => {
    barCountRef.current = 0;
    userAdjustedViewportRef.current = false;
  }, [timeframe]);

  useLayoutEffect(() => {
    chartRef.current?.timeScale().applyOptions({
      secondsVisible: timeframe === "1m",
    });
  }, [timeframe]);

  const resetViewport = () => {
    userAdjustedViewportRef.current = false;
    const chart = chartRef.current;
    if (chart && barCountRef.current > 0) {
      suppressViewportTrackingRef.current = true;
      applyDefaultViewport(chart, barCountRef.current, timeframe);
    }
  };

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
          <button type="button" className="btn-ghost btn-sm" onClick={resetViewport}>
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
