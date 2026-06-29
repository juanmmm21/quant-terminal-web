#!/usr/bin/env python3
"""
Materializa velas OHLCV en el lakehouse local usando market-data-lakehouse.

Descarga histórico paginado de Binance (1m + 1h) e ingesta vía subprocess.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_BINANCE_BATCH = 1000


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


def fetch_klines_batch(
    symbol: str,
    interval: str,
    *,
    limit: int,
    end_time_ms: int | None = None,
) -> list[list[object]]:
    if limit <= 0 or limit > MAX_BINANCE_BATCH:
        raise ValueError(f"limit must be 1..{MAX_BINANCE_BATCH}")
    params = f"symbol={symbol}&interval={interval}&limit={limit}"
    if end_time_ms is not None:
        params += f"&endTime={end_time_ms}"
    url = f"{BINANCE_KLINES_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to fetch binance klines: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError("unexpected binance klines response")
    return payload


def fetch_klines_paginated(symbol: str, interval: str, *, max_candles: int) -> list[list[object]]:
    """Descarga velas hacia atrás en el tiempo (máx. max_candles)."""
    if max_candles <= 0:
        return []

    collected: list[list[object]] = []
    end_time_ms: int | None = None

    while len(collected) < max_candles:
        batch_limit = min(MAX_BINANCE_BATCH, max_candles - len(collected))
        batch = fetch_klines_batch(
            symbol,
            interval,
            limit=batch_limit,
            end_time_ms=end_time_ms,
        )
        if not batch:
            break
        collected = batch + collected
        oldest_open_ms = int(batch[0][0])
        end_time_ms = oldest_open_ms - 1
        if len(batch) < batch_limit:
            break
        time.sleep(0.12)

    if len(collected) > max_candles:
        return collected[-max_candles:]
    return collected


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


def candles_for_days(interval: str, days: int) -> int:
    if days <= 0:
        return 0
    if interval == "1m":
        return days * 24 * 60
    if interval == "5m":
        return days * 24 * 12
    if interval == "1h":
        return days * 24
    raise ValueError(f"unsupported interval for bootstrap: {interval}")


def write_ticks(path: Path, symbol: str, klines: list[list[object]], *, id_offset: int = 0) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index, kline in enumerate(klines):
            tick = kline_to_tick(symbol, kline, id_offset + index)
            handle.write(json.dumps(tick) + "\n")
    return len(klines)


def ingest_ticks(ticks_path: Path, lake_root: Path, *, symbol: str) -> None:
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
        "500",
    ]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def bootstrap_history(
    *,
    symbol: str = "BTCUSDT",
    days_1m: int = 90,
    days_1h: int = 730,
    lake_root: Path | None = None,
) -> None:
    root = project_root()
    lake = lake_root or (root / "data" / "lake")
    work = root / "data" / "bootstrap"
    work.mkdir(parents=True, exist_ok=True)

    symbol = symbol.upper()
    total_ticks = 0

    if days_1h > 0:
        target_1h = candles_for_days("1h", days_1h)
        print(f"downloading ~{target_1h} hourly candles ({days_1h} days)...")
        klines_1h = fetch_klines_paginated(symbol, "1h", max_candles=target_1h)
        ticks_1h = work / "ticks_1h.jsonl"
        written = write_ticks(ticks_1h, symbol, klines_1h)
        print(f"ingesting {written} hourly-derived ticks...")
        ingest_ticks(ticks_1h, lake, symbol=symbol)
        total_ticks += written

    if days_1m > 0:
        target_1m = candles_for_days("1m", days_1m)
        print(f"downloading ~{target_1m} minute candles ({days_1m} days)...")
        klines_1m = fetch_klines_paginated(symbol, "1m", max_candles=target_1m)
        ticks_1m = work / "ticks_1m.jsonl"
        written = write_ticks(ticks_1m, symbol, klines_1m, id_offset=total_ticks)
        print(f"ingesting {written} minute-derived ticks...")
        ingest_ticks(ticks_1m, lake, symbol=symbol)
        total_ticks += written

    print(f"lakehouse ready at {lake} ({total_ticks} bootstrap ticks)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap lakehouse with Binance historical klines")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--days-1m",
        type=int,
        default=90,
        help="días de histórico en velas de 1 minuto (0 = omitir)",
    )
    parser.add_argument(
        "--days-1h",
        type=int,
        default=730,
        help="días de histórico en velas de 1 hora (0 = omitir)",
    )
    args = parser.parse_args()
    bootstrap_history(symbol=args.symbol.upper(), days_1m=args.days_1m, days_1h=args.days_1h)


if __name__ == "__main__":
    main()
