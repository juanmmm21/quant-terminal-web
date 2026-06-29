#!/usr/bin/env python3
"""Crea analysis cache de prueba para tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def write_sample_analysis(path: Path, *, timeframe: str = "1h") -> None:
    now = datetime.now(tz=UTC).isoformat()
    payload = {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "currency": "USDT",
        "last_price": "60152.00",
        "updated_at": now,
        "recommendation": {
            "verdict": "hold",
            "action": "hold",
            "side": None,
            "confidence": 0.42,
            "reason": "RSI en zona neutral",
            "strategy_id": "macd_crossover",
            "reference_price": "60152.00",
            "event_time": now,
        },
        "indicators": {
            "rsi": 52.0,
            "macd_line": -10.5,
            "signal_line": -8.2,
            "sma_20": 60000.0,
            "ema_20": 60100.0,
        },
        "training": {
            "symbol": "BTCUSDT",
            "bars_analyzed": 100,
            "signal_count": 4,
            "enter_signals": 2,
            "exit_signals": 2,
            "directional_win_rate": "0.5",
            "selected_strategy": "macd_crossover",
            "trained_at": now,
        },
        "signals": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
