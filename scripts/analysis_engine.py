#!/usr/bin/env python3
"""
Motor de análisis: entrena sobre histórico y emite recomendación sobre precio actual.

Usa ta-indicators-from-scratch + alpha-signal-generator vía subprocess.
Escribe data/runtime/analysis_{timeframe}.json (sin simulación de cuenta).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ecosystem_tools import (
    count_lakehouse_candles,
    export_lakehouse_candles_jsonl,
    indicators_json_to_candles_jsonl,
    project_root,
    resolve_cli,
    run_cli,
)

logger = logging.getLogger(__name__)

STRATEGIES = ("rsi_mean_reversion", "macd_crossover")
SUPPORTED_UI_TIMEFRAMES = ("1m", "5m", "10m", "15m", "1h")
LAKEHOUSE_TIMEFRAMES = ("1m", "5m", "1h")
DEFAULT_ANALYSIS_BAR_LIMIT = int(os.environ.get("TERMINAL_ANALYSIS_CANDLE_LIMIT", "0"))


def runtime_dir() -> Path:
    path = project_root() / "data" / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def work_dir() -> Path:
    path = runtime_dir() / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lakehouse_timeframe_for(ui_timeframe: str) -> str:
    if ui_timeframe in ("10m", "15m"):
        return "1m"
    return ui_timeframe


def run_signals(
    enriched_candles: Path,
    *,
    symbol: str,
    strategy: str,
    output: Path,
) -> list[dict[str, Any]]:
    alpha_cli = resolve_cli("alpha-signal-generator")
    run_cli(
        [
            alpha_cli,
            "run",
            "--candles",
            str(enriched_candles),
            "--symbol",
            symbol,
            "--strategy",
            strategy,
            "--output",
            str(output),
        ]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("signals output must be a JSON array")
    return payload


def pick_best_strategy(
    enriched_candles: Path,
    *,
    symbol: str,
    work: Path,
) -> tuple[str, list[dict[str, Any]]]:
    best_strategy = STRATEGIES[0]
    best_signals: list[dict[str, Any]] = []
    best_score = -1.0

    for strategy in STRATEGIES:
        signals_path = work / f"signals_{strategy}.json"
        signals = run_signals(
            enriched_candles,
            symbol=symbol,
            strategy=strategy,
            output=signals_path,
        )
        score = _training_score(signals)
        logger.info("strategy %s score=%.3f signals=%s", strategy, score, len(signals))
        if score > best_score:
            best_score = score
            best_strategy = strategy
            best_signals = signals

    return best_strategy, best_signals


def _training_score(signals: list[dict[str, Any]]) -> float:
    if not signals:
        return 0.0
    enters = [signal for signal in signals if signal.get("action") == "enter"]
    exits = [signal for signal in signals if signal.get("action") == "exit"]
    if not enters:
        return float(len(signals)) * 0.01
    win_rate = _directional_win_rate(signals)
    return win_rate * 2.0 + min(len(signals), 50) * 0.01


def _directional_win_rate(signals: list[dict[str, Any]]) -> float:
    sorted_signals = sorted(signals, key=lambda item: str(item.get("event_time", "")))
    wins = 0
    rounds = 0
    last_enter_price: Decimal | None = None
    for signal in sorted_signals:
        action = signal.get("action")
        if action == "enter":
            try:
                last_enter_price = Decimal(str(signal.get("reference_price", "0")))
            except Exception:
                last_enter_price = None
        elif action == "exit" and last_enter_price is not None:
            try:
                exit_price = Decimal(str(signal.get("reference_price", "0")))
                if exit_price > last_enter_price:
                    wins += 1
                rounds += 1
            except Exception:
                pass
            last_enter_price = None
    if rounds == 0:
        return 0.0
    return wins / rounds


def extract_last_indicators(indicators_json: Path, candles_jsonl: Path) -> dict[str, float | None]:
    payload = json.loads(indicators_json.read_text(encoding="utf-8"))
    indicators = payload.get("indicators", {}) if isinstance(payload, dict) else {}
    result: dict[str, float | None] = {
        "rsi": _last_value(indicators.get("rsi", {}).get("values", [])),
        "macd_line": _last_value(indicators.get("macd", {}).get("macd_line", [])),
        "signal_line": _last_value(indicators.get("macd", {}).get("signal_line", [])),
        "sma_20": _last_value(indicators.get("sma", {}).get("values", [])),
        "ema_20": _last_value(indicators.get("ema", {}).get("values", [])),
    }
    if result["rsi"] is None:
        lines = [line for line in candles_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            last = json.loads(lines[-1])
            if isinstance(last, dict) and last.get("rsi") is not None:
                result["rsi"] = float(last["rsi"])
    return result


def _last_value(values: list[object]) -> float | None:
    for value in reversed(values):
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def derive_recommendation(
    signals: list[dict[str, Any]],
    *,
    strategy_id: str,
    indicators: dict[str, float | None],
    last_price: str,
) -> dict[str, Any]:
    sorted_signals = sorted(signals, key=lambda item: str(item.get("event_time", "")))
    in_long = False
    last_signal: dict[str, Any] | None = None
    for signal in sorted_signals:
        action = signal.get("action")
        if action == "enter" and signal.get("side") == "long":
            in_long = True
            last_signal = signal
        elif action == "exit":
            in_long = False
            last_signal = signal

    if last_signal and last_signal.get("action") == "enter" and in_long:
        return {
            "verdict": "buy",
            "action": "enter",
            "side": "long",
            "confidence": float(last_signal.get("confidence", 0.5)),
            "reason": str(last_signal.get("reason", "señal de entrada larga")),
            "strategy_id": strategy_id,
            "reference_price": str(last_signal.get("reference_price", last_price)),
            "event_time": last_signal.get("event_time"),
        }
    if last_signal and last_signal.get("action") == "exit":
        return {
            "verdict": "sell",
            "action": "exit",
            "side": "long",
            "confidence": float(last_signal.get("confidence", 0.5)),
            "reason": str(last_signal.get("reason", "señal de salida")),
            "strategy_id": strategy_id,
            "reference_price": str(last_signal.get("reference_price", last_price)),
            "event_time": last_signal.get("event_time"),
        }

    rsi = indicators.get("rsi")
    reason = "sin señal activa — esperar confirmación"
    if rsi is not None:
        if rsi < 35:
            reason = f"RSI {rsi:.1f} cerca de sobreventa — vigilar entrada"
        elif rsi > 65:
            reason = f"RSI {rsi:.1f} cerca de sobrecompra — vigilar salida"
        else:
            reason = f"RSI {rsi:.1f} en zona neutral"

    return {
        "verdict": "hold",
        "action": "hold",
        "side": None,
        "confidence": 0.35,
        "reason": reason,
        "strategy_id": strategy_id,
        "reference_price": last_price,
        "event_time": datetime.now(tz=UTC).isoformat(),
    }


def read_last_price(ticks_path: Path, fallback: str) -> str:
    if not ticks_path.exists():
        return fallback
    try:
        lines = [line for line in ticks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return fallback
        tick = json.loads(lines[-1])
        if isinstance(tick, dict) and tick.get("price"):
            return str(tick["price"])
    except (OSError, json.JSONDecodeError):
        return fallback
    return fallback


def _export_limit(lake_root: Path, symbol: str, ui_timeframe: str, candle_limit: int) -> int:
    lake_tf = lakehouse_timeframe_for(ui_timeframe)
    source_tf = "1m" if ui_timeframe in ("10m", "15m") else lake_tf
    available = count_lakehouse_candles(lake_root, symbol=symbol, timeframe=source_tf)
    if available <= 0:
        return max(candle_limit, 500)
    if candle_limit <= 0:
        return available
    return min(candle_limit, available)


def run_analysis(
    *,
    symbol: str = "BTCUSDT",
    ui_timeframe: str = "1h",
    candle_limit: int = DEFAULT_ANALYSIS_BAR_LIMIT,
) -> Path:
    if ui_timeframe not in SUPPORTED_UI_TIMEFRAMES:
        raise ValueError(f"unsupported timeframe: {ui_timeframe}")

    root = project_root()
    lake_root = root / "data" / "lake"
    ticks_path = root / "data" / "live" / "ticks.jsonl"
    work = work_dir()
    lake_tf = lakehouse_timeframe_for(ui_timeframe)

    candles_jsonl = work / f"candles_{ui_timeframe}.jsonl"
    export_limit = _export_limit(lake_root, symbol, ui_timeframe, candle_limit)
    logger.info("exporting %s bars for %s (%s)", export_limit, ui_timeframe, lake_tf)
    export_lakehouse_candles_jsonl(
        lake_root,
        candles_jsonl,
        symbol=symbol,
        timeframe=lake_tf,
        limit=export_limit,
    )
    bar_count = sum(1 for line in candles_jsonl.read_text(encoding="utf-8").splitlines() if line.strip())

    ta_cli = resolve_cli("ta-indicators-from-scratch")
    indicators_json = work / f"indicators_{ui_timeframe}.json"
    run_cli(
        [
            ta_cli,
            "compute",
            "--input",
            str(candles_jsonl),
            "--indicator",
            "all",
            "--output",
            str(indicators_json),
        ]
    )

    enriched = work / f"candles_enriched_{ui_timeframe}.jsonl"
    indicators_json_to_candles_jsonl(
        indicators_json,
        enriched,
        event_times_source=candles_jsonl,
    )

    strategy, signals = pick_best_strategy(enriched, symbol=symbol, work=work)
    indicators = extract_last_indicators(indicators_json, enriched)
    last_candle = json.loads(
        [line for line in candles_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()][-1]
    )
    fallback_price = str(last_candle.get("close", "0")) if isinstance(last_candle, dict) else "0"
    last_price = read_last_price(ticks_path, fallback_price)

    recommendation = derive_recommendation(
        signals,
        strategy_id=strategy,
        indicators=indicators,
        last_price=last_price,
    )

    enters = sum(1 for signal in signals if signal.get("action") == "enter")
    exits = sum(1 for signal in signals if signal.get("action") == "exit")
    now = datetime.now(tz=UTC).isoformat()

    payload = {
        "symbol": symbol,
        "timeframe": ui_timeframe,
        "currency": "USDT",
        "last_price": last_price,
        "updated_at": now,
        "recommendation": recommendation,
        "indicators": indicators,
        "training": {
            "symbol": symbol,
            "bars_analyzed": bar_count,
            "signal_count": len(signals),
            "enter_signals": enters,
            "exit_signals": exits,
            "directional_win_rate": str(_directional_win_rate(signals)),
            "selected_strategy": strategy,
            "trained_at": now,
        },
        "signals": signals[-120:],
    }

    output = runtime_dir() / f"analysis_{ui_timeframe}.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("wrote analysis %s (%s signals, verdict=%s)", output, len(signals), recommendation["verdict"])
    return output


def run_all_timeframes(*, symbol: str = "BTCUSDT", candle_limit: int = DEFAULT_ANALYSIS_BAR_LIMIT) -> None:
    manifest = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "symbol": symbol,
        "timeframes": list(SUPPORTED_UI_TIMEFRAMES),
        "modules": [
            "market-data-lakehouse",
            "ta-indicators-from-scratch",
            "alpha-signal-generator",
        ],
    }
    for timeframe in SUPPORTED_UI_TIMEFRAMES:
        try:
            run_analysis(symbol=symbol, ui_timeframe=timeframe, candle_limit=candle_limit)
        except Exception as exc:
            logger.error("analysis failed for %s: %s", timeframe, exc)
    (runtime_dir() / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train on history and emit live recommendation cache")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default=None, help="UI timeframe or all if omitted")
    parser.add_argument("--limit", type=int, default=DEFAULT_ANALYSIS_BAR_LIMIT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    symbol = args.symbol.upper()
    if args.timeframe:
        run_analysis(symbol=symbol, ui_timeframe=args.timeframe, candle_limit=args.limit)
    else:
        run_all_timeframes(symbol=symbol)


if __name__ == "__main__":
    main()
