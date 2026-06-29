import { useMemo, useRef, useState } from "react";

import type { Candle } from "../types/api";
import { formatDateTime, formatMoney } from "../utils/format";

interface CandlestickChartProps {
  symbol: string;
  interval: string;
  currency: string;
  lastPrice: string;
  changePct: string;
  candles: Candle[];
}

interface HoverState {
  index: number;
  x: number;
  y: number;
}

const CHART_WIDTH = 960;
const PRICE_HEIGHT = 320;
const VOLUME_HEIGHT = 72;
const PADDING = { top: 16, right: 72, bottom: 28, left: 12 };
const TOTAL_HEIGHT = PRICE_HEIGHT + VOLUME_HEIGHT + 24;

export function CandlestickChart({
  symbol,
  interval,
  currency,
  lastPrice,
  changePct,
  candles,
}: CandlestickChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  const layout = useMemo(() => {
    if (candles.length === 0) {
      return null;
    }

    const plotWidth = CHART_WIDTH - PADDING.left - PADDING.right;
    const highs = candles.map((c) => Number(c.high));
    const lows = candles.map((c) => Number(c.low));
    const volumes = candles.map((c) => Number(c.volume));
    const minPrice = Math.min(...lows);
    const maxPrice = Math.max(...highs);
    const pricePad = (maxPrice - minPrice) * 0.06 || maxPrice * 0.001;
    const yMin = minPrice - pricePad;
    const yMax = maxPrice + pricePad;
    const maxVolume = Math.max(...volumes, 1);
    const slot = plotWidth / candles.length;
    const bodyWidth = Math.max(3, slot * 0.62);

    const priceY = (value: number) =>
      PADDING.top + ((yMax - value) / (yMax - yMin)) * (PRICE_HEIGHT - PADDING.top);

    const volumeY = (value: number) =>
      PRICE_HEIGHT + 12 + (1 - value / maxVolume) * (VOLUME_HEIGHT - 8);

    const candleX = (index: number) => PADDING.left + index * slot + slot / 2;

    const priceTicks = 5;
    const yTicks = Array.from({ length: priceTicks }, (_, i) => {
      const ratio = i / (priceTicks - 1);
      const value = yMax - ratio * (yMax - yMin);
      return { value, y: priceY(value) };
    });

    return {
      plotWidth,
      slot,
      bodyWidth,
      yMin,
      yMax,
      maxVolume,
      priceY,
      volumeY,
      candleX,
      yTicks,
    };
  }, [candles]);

  const changeNum = Number(changePct);
  const changeLabel = Number.isNaN(changeNum)
    ? changePct
    : `${changeNum >= 0 ? "+" : ""}${(changeNum * 100).toFixed(2)} %`;

  const handleMove = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!layout || !svgRef.current) {
      return;
    }
    const rect = svgRef.current.getBoundingClientRect();
    const relativeX = ((event.clientX - rect.left) / rect.width) * CHART_WIDTH;
    const index = Math.floor((relativeX - PADDING.left) / layout.slot);
    if (index < 0 || index >= candles.length) {
      setHover(null);
      return;
    }
    setHover({ index, x: layout.candleX(index), y: event.clientY - rect.top });
  };

  const active = hover ? candles[hover.index] : candles[candles.length - 1];
  const activeIndex = hover?.index ?? candles.length - 1;
  const bullish = active ? Number(active.close) >= Number(active.open) : true;

  if (!layout || candles.length === 0) {
    return <p className="empty-state">Sin datos de velas para mostrar.</p>;
  }

  return (
    <section className="chart-panel">
      <header className="chart-header">
        <div>
          <h2>{symbol}</h2>
          <p className="chart-subtitle">Velas {interval} · precio de mercado en {currency}</p>
        </div>
        <div className="chart-price-block">
          <span className="chart-last-price">{formatMoney(lastPrice)} {currency}</span>
          <span className={changeNum >= 0 ? "price-up" : "price-down"}>{changeLabel}</span>
        </div>
      </header>

      <div className="ohlc-legend" aria-live="polite">
        <span>O {formatMoney(active.open)}</span>
        <span>H {formatMoney(active.high)}</span>
        <span>L {formatMoney(active.low)}</span>
        <span>C {formatMoney(active.close)}</span>
        <span>Vol {Number(active.volume).toLocaleString("es-ES")}</span>
        <span className="ohlc-time">{formatDateTime(active.open_time)}</span>
      </div>

      <svg
        ref={svgRef}
        className="candlestick-chart"
        viewBox={`0 0 ${CHART_WIDTH} ${TOTAL_HEIGHT}`}
        role="img"
        aria-label={`Gráfico de velas de ${symbol}`}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        <rect x="0" y="0" width={CHART_WIDTH} height={TOTAL_HEIGHT} className="chart-canvas" />

        {layout.yTicks.map((tick) => (
          <g key={tick.value}>
            <line
              x1={PADDING.left}
              x2={CHART_WIDTH - PADDING.right}
              y1={tick.y}
              y2={tick.y}
              className="grid-line"
            />
            <text x={CHART_WIDTH - PADDING.right + 8} y={tick.y + 4} className="axis-label">
              {formatMoney(String(tick.value), 0)}
            </text>
          </g>
        ))}

        {candles.map((candle, index) => {
          const open = Number(candle.open);
          const close = Number(candle.close);
          const high = Number(candle.high);
          const low = Number(candle.low);
          const up = close >= open;
          const x = layout.candleX(index);
          const bodyTop = layout.priceY(Math.max(open, close));
          const bodyBottom = layout.priceY(Math.min(open, close));
          const bodyHeight = Math.max(1.5, bodyBottom - bodyTop);
          const volumeHeight = (PRICE_HEIGHT + VOLUME_HEIGHT + 4) - layout.volumeY(Number(candle.volume));

          return (
            <g key={candle.open_time}>
              <line
                x1={x}
                x2={x}
                y1={layout.priceY(high)}
                y2={layout.priceY(low)}
                className={up ? "wick-up" : "wick-down"}
              />
              <rect
                x={x - layout.bodyWidth / 2}
                y={bodyTop}
                width={layout.bodyWidth}
                height={bodyHeight}
                className={up ? "body-up" : "body-down"}
              />
              <rect
                x={x - layout.bodyWidth / 2}
                y={layout.volumeY(Number(candle.volume))}
                width={layout.bodyWidth}
                height={volumeHeight}
                className={up ? "volume-up" : "volume-down"}
                opacity={index === activeIndex ? 1 : 0.55}
              />
            </g>
          );
        })}

        <line
          x1={PADDING.left}
          x2={CHART_WIDTH - PADDING.right}
          y1={layout.priceY(Number(lastPrice))}
          y2={layout.priceY(Number(lastPrice))}
          className="last-price-line"
        />

        {hover ? (
          <line x1={hover.x} x2={hover.x} y1={PADDING.top} y2={PRICE_HEIGHT + VOLUME_HEIGHT + 8} className="crosshair" />
        ) : null}
      </svg>
      <p className={`candle-trend-hint ${bullish ? "price-up" : "price-down"}`}>
        Vela seleccionada: {bullish ? "alcista" : "bajista"}
        {hover ? "" : " (última)"}
      </p>
    </section>
  );
}
