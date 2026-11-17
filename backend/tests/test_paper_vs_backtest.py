from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from paper_vs_backtest import build_comparison, downsample

T0 = datetime(2026, 11, 10, tzinfo=UTC)


def test_downsample_keeps_the_last_point() -> None:
    points = [{"at": str(i)} for i in range(1234)]
    picked = downsample(points, limit=100)
    assert len(picked) == 100 and picked[-1] == points[-1]


@pytest.mark.skipif(shutil.which("event-driven-backtester") is None, reason="CLI not installed")
def test_comparison_uses_the_same_period_size_and_strategy(tmp_path: Path) -> None:
    runtime = tmp_path / "data" / "runtime"
    work = runtime / "work"
    paper = tmp_path / "data" / "paper"
    work.mkdir(parents=True)
    paper.mkdir(parents=True)
    (runtime / "paper_promotion.json").write_text(json.dumps({
        "active": True, "symbol": "BTCUSDT", "strategy": "rsi_mean_reversion",
        "timeframe": "1h", "promoted_at": T0.isoformat(), "gate_passed": False,
    }), encoding="utf-8")
    (paper / "state.json").write_text(json.dumps({
        "initial_cash": "10000", "started_at": (T0 - timedelta(days=1)).isoformat(),
    }), encoding="utf-8")
    (paper / "equity.jsonl").write_text("\n".join(json.dumps(
        {"at": (T0 + timedelta(hours=h)).isoformat(), "equity": str(10000 + h)}
    ) for h in range(48)), encoding="utf-8")
    (paper / "fills.jsonl").write_text(json.dumps({
        "filled_at": (T0 + timedelta(hours=2)).isoformat(), "commission": "0.065",
    }), encoding="utf-8")
    with (work / "candles_1h.jsonl").open("w", encoding="utf-8") as handle:
        for h in range(-24, 48):
            handle.write(json.dumps({"event_time": (T0 + timedelta(hours=h)).isoformat(),
                                     "close": 65000 + h * 10, "volume": 1}) + "\n")
    signals = [
        {"strategy_id": "rsi_mean_reversion", "symbol": "BTCUSDT", "action": action,
         "side": "long", "confidence": 0.5, "reason": "t",
         "event_time": (T0 + timedelta(hours=h)).isoformat()}
        for h, action in ((-5, "enter"), (3, "enter"), (20, "exit"))
    ]
    (work / "signals_rsi_mean_reversion_1h.json").write_text(json.dumps(signals),
                                                             encoding="utf-8")
    report = build_comparison(tmp_path, now=T0 + timedelta(hours=47))
    assert report["paper"]["pnl"] == "47"
    assert report["backtest"]["signals_in_period"] == 2  # the pre-promotion entry is excluded
    assert report["backtest"]["fills"] == 2
    assert report["gate_passed"] is False
    assert "testnet" in report["disclaimer"]
