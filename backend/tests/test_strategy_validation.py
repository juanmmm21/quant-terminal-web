from __future__ import annotations

import json
import math
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ecosystem_tools import dedupe_candle_rows, indicator_series
from strategy_validation import (
    candles_to_close_ticks,
    pbo_splits,
    run_validation,
    shift_signals_to_bar_close,
)

T0 = datetime(2025, 1, 1, tzinfo=UTC)


def test_ticks_and_signals_land_on_the_bar_close() -> None:
    candles = [{"event_time": T0.isoformat(), "close": 101.0, "volume": 2.0}]
    ticks = candles_to_close_ticks(candles, symbol="BTCUSDT", bar_seconds=3600)
    signals = shift_signals_to_bar_close(
        [
            {"action": "enter", "side": "long", "event_time": T0.isoformat()},
            {"action": "hold", "event_time": T0.isoformat()},
        ],
        bar_seconds=3600,
    )
    close = (T0 + timedelta(hours=1)).isoformat()
    assert ticks[0]["event_time"] == close
    assert ticks[0]["price"] == "101.0"
    # The signal computed from this bar's close may only be filled at that close or later.
    assert [s["event_time"] for s in signals] == [close]


def test_pbo_split_count_adapts_to_history() -> None:
    assert pbo_splits(17_519) == 16
    assert pbo_splits(200) == 10
    assert pbo_splits(30) == 2


def test_indicator_series_reads_ta_cli_layout() -> None:
    block = {"rsi": {"rsi": [None, 55.0]}, "sma": {"values": [1.0]}}
    assert indicator_series(block, "rsi") == [None, 55.0]
    assert indicator_series(block, "sma") == [1.0]
    assert indicator_series(block, "ema") == []


def test_dedupe_keeps_most_complete_bar() -> None:
    rows = [
        {"open_time": "a", "trade_count": 4, "close": "1"},
        {"open_time": "a", "trade_count": 1, "close": "2"},
        {"open_time": "b", "trade_count": 1, "close": "3"},
    ]
    assert [row["close"] for row in dedupe_candle_rows(rows)] == ["1", "3"]


CLIS = ("event-driven-backtester", "quant-metrics-calculator")


@pytest.mark.skipif(
    any(shutil.which(cli) is None for cli in CLIS),
    reason="ecosystem CLIs not installed",
)
def test_end_to_end_with_real_clis(tmp_path: Path) -> None:
    bars = 400
    candles = tmp_path / "candles.jsonl"
    with candles.open("w", encoding="utf-8") as handle:
        for i in range(bars):
            price = 100 + 10 * math.sin(i / 7) + i * 0.05
            handle.write(
                json.dumps(
                    {
                        "event_time": (T0 + timedelta(hours=i)).isoformat(),
                        "close": price,
                        "volume": 1.0,
                    }
                )
                + "\n"
            )

    def cycle(name: str, every: int, hold: int) -> Path:
        rows = []
        for start in range(0, bars - hold - 1, every):
            for offset, action in ((0, "enter"), (hold, "exit")):
                rows.append(
                    {
                        "strategy_id": name,
                        "symbol": "BTCUSDT",
                        "action": action,
                        "side": "long",
                        "confidence": 0.5,
                        "reason": "test",
                        "event_time": (T0 + timedelta(hours=start + offset)).isoformat(),
                    }
                )
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        return path

    idle = tmp_path / "idle.json"
    idle.write_text("[]", encoding="utf-8")
    report = run_validation(
        symbol="BTCUSDT",
        timeframe="1h",
        bar_seconds=3600,
        candles_jsonl=candles,
        signal_files={"fast": cycle("fast", 5, 3), "slow": cycle("slow", 14, 7), "idle": idle},
        selected="fast",
        n_trials=10,
        work=tmp_path / "work",
    )
    assert report["excluded_candidates"] == ["idle"]
    assert report["candidates"] == ["fast", "slow"]
    assert report["n_trials"] == 10
    assert 0.0 <= report["deflated_sharpe_ratio"] <= 1.0
    assert 0.0 <= report["pbo"] <= 1.0
    assert report["purged_kfold"]["folds"] == 5
    assert report["walk_forward"]["folds"] == 5
    assert report["kind"] == "backtest"
    assert len(report["report_id"]) == 16
