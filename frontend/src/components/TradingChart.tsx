import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { AnalysisSnapshot, Candle, Timeframe } from "../types/api";
import { formatDateTime, formatMoney } from "../utils/format";

export const TIMEFRAMES: Timeframe[] = ["1m", "5m", "10m", "15m", "1h"];

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

function toChartTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

function verdictLabel(verdict: string): string {
  const map: Record<string, string> = {
    buy: "COMPRAR",
    sell: "VENDER",
    hold: "MANTENER",
  };
  return map[verdict] ?? verdict.toUpperCase();
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
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#334155",
      },
      grid: {
        vertLines: { color: "#eef2f7" },
        horzLines: { color: "#eef2f7" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#dbe3ef" },
      timeScale: {
        borderColor: "#dbe3ef",
        timeVisible: true,
        secondsVisible: timeframe === "1m",
      },
      handleScroll: { vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#0d9f6e",
      downColor: "#dc3f4e",
      borderUpColor: "#0d9f6e",
      borderDownColor: "#dc3f4e",
      wickUpColor: "#0d9f6e",
      wickDownColor: "#dc3f4e",
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

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        chart.applyOptions({ width, height });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [timeframe]);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const chart = chartRef.current;
    if (!candleSeries || !volumeSeries || !chart || candles.length === 0) {
      return;
    }

    candleSeries.setData(
      candles.map((candle) => ({
        time: toChartTime(candle.open_time),
        open: Number(candle.open),
        high: Number(candle.high),
        low: Number(candle.low),
        close: Number(candle.close),
      })),
    );

    volumeSeries.setData(
      candles.map((candle) => {
        const up = Number(candle.close) >= Number(candle.open);
        return {
          time: toChartTime(candle.open_time),
          value: Number(candle.volume),
          color: up ? "rgba(13, 159, 110, 0.45)" : "rgba(220, 63, 78, 0.45)",
        };
      }),
    );

    const markers: SeriesMarker<Time>[] = (analysis?.signals ?? []).map((signal) => {
      const isBuy = signal.action === "enter";
      return {
        time: toChartTime(signal.event_time),
        position: isBuy ? "belowBar" : "aboveBar",
        color: isBuy ? "#0d9f6e" : "#dc3f4e",
        shape: isBuy ? "arrowUp" : "arrowDown",
        text: isBuy ? "ENT" : "SAL",
      };
    });
    candleSeries.setMarkers(markers);
    chart.timeScale().fitContent();
  }, [candles, analysis]);

  const toggleFullscreen = async () => {
    const node = containerRef.current?.parentElement;
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

  return (
    <section className={`chart-panel trading-chart-panel ${fullscreen ? "is-fullscreen" : ""}`}>
      <header className="chart-header">
        <div>
          <h2>{symbol}</h2>
          <p className="chart-subtitle">Análisis en tiempo real · {currency}</p>
        </div>
        <div className="chart-price-block">
          <span className="chart-last-price">
            {formatMoney(lastPrice)} {currency}
          </span>
          <span className={changeNum >= 0 ? "price-up" : "price-down"}>{changeLabel}</span>
          {recommendation ? (
            <span className={`verdict-pill verdict-${recommendation.verdict}`}>
              {verdictLabel(recommendation.verdict)} · {(recommendation.confidence * 100).toFixed(0)}%
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
          <button type="button" className="btn-ghost btn-sm" onClick={() => chartRef.current?.timeScale().fitContent()}>
            Ajustar zoom
          </button>
          <button type="button" className="btn-ghost btn-sm" onClick={() => void toggleFullscreen()}>
            {fullscreen ? "Salir pantalla completa" : "Pantalla completa"}
          </button>
        </div>
      </div>

      <div className="chart-canvas-wrap" ref={containerRef} style={{ height: fullscreen ? "calc(100vh - 120px)" : 460 }} />

      {recommendation ? (
        <p className="recommendation-hint">
          <strong>{verdictLabel(recommendation.verdict)}</strong> — {recommendation.reason}
          <span className="hint-meta">
            Estrategia {recommendation.strategy_id}
            {recommendation.event_time ? ` · ${formatDateTime(recommendation.event_time)}` : ""}
          </span>
        </p>
      ) : (
        <p className="recommendation-hint muted">Esperando análisis del motor…</p>
      )}
    </section>
  );
}
