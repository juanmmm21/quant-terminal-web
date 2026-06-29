#!/usr/bin/env python3
"""
Materializa velas OHLCV en el lakehouse local usando market-data-lakehouse.

1. Descarga klines públicas de Binance (solo en bootstrap, no en la API).
2. Convierte cada vela en un tick compatible con el ecosistema.
3. Ejecuta `market-data-lakehouse ingest` vía subprocess (sin imports cruzados).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_lakehouse_cli() -> str:
    found = shutil.which("market-data-lakehouse")
    if found:
        return found
    sibling = project_root().parent / "market-data-lakehouse" / ".venv" / "bin" / "market-data-lakehouse"
    if sibling.exists():
        return str(sibling)
    raise SystemExit(
        "market-data-lakehouse no está en PATH. Instálalo desde ../market-data-lakehouse "
        "o actívalo en un venv."
    )


def fetch_klines(symbol: str, interval: str, limit: int) -> list[list[object]]:
    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval={interval}&limit={limit}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SystemExit(f"failed to fetch binance klines: {exc}") from exc
    if not isinstance(payload, list):
        raise SystemExit("unexpected binance klines response")
    return payload


def kline_to_tick(symbol: str, kline: list[object], index: int) -> dict[str, str]:
    open_time_ms = int(kline[0])
    close_price = str(kline[4])
    volume = str(kline[5])
    event_time = datetime.fromtimestamp(open_time_ms / 1000.0, tz=UTC).isoformat()
    return {
        "exchange": "binance",
        "symbol": symbol,
        "trade_id": f"bootstrap-{index}",
        "price": close_price,
        "quantity": volume,
        "side": "buy",
        "event_time": event_time,
    }


def main() -> None:
    symbol = "BTCUSDT"
    interval = "1m"
    limit = 1000
    root = project_root()
    lake_root = root / "data" / "lake"
    ticks_path = root / "data" / "bootstrap_ticks.jsonl"

    ticks_path.parent.mkdir(parents=True, exist_ok=True)
    klines = fetch_klines(symbol=symbol, interval=interval, limit=limit)

    with ticks_path.open("w", encoding="utf-8") as handle:
        for index, kline in enumerate(klines):
            tick = kline_to_tick(symbol, kline, index)
            handle.write(json.dumps(tick) + "\n")

    cli = resolve_lakehouse_cli()
    cmd = [
        cli,
        "ingest",
        "--input",
        str(ticks_path),
        "--root",
        str(lake_root),
        "--exchange",
        "binance",
        "--symbol",
        symbol,
        "--timeframes",
        "1m",
        "5m",
        "1h",
        "--flush-batch-size",
        "200",
    ]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"lakehouse ready at {lake_root}")
    print("start API and run: python scripts/tick_bridge.py  # for live last price")


if __name__ == "__main__":
    main()
