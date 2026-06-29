#!/usr/bin/env python3
"""
Puente live: escribe ticks JSONL compatibles con market-data-lakehouse.

Formato alineado con websocket-feed-handler (TradeEvent). La API lee el último
precio desde data/live/ticks.jsonl mientras las velas vienen del lakehouse.

Requiere: pip install websockets
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


async def stream_binance_trades(symbol: str, output: Path) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("install websockets: pip install websockets") from exc

    stream = symbol.lower() + "@trade"
    url = f"wss://stream.binance.com:9443/ws/{stream}"
    output.parent.mkdir(parents=True, exist_ok=True)

    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        logger.info("connected to %s", url)
        with output.open("a", encoding="utf-8") as handle:
            while True:
                raw = await ws.recv()
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                price = payload.get("p")
                quantity = payload.get("q")
                trade_id = payload.get("t")
                event_time_ms = payload.get("T")
                is_buyer_maker = payload.get("m")
                if not all(isinstance(value, (str, int, bool)) for value in (price, quantity, trade_id, event_time_ms, is_buyer_maker)):
                    continue
                event_time = datetime.fromtimestamp(int(event_time_ms) / 1000.0, tz=UTC).isoformat()
                tick = {
                    "exchange": "binance",
                    "symbol": symbol,
                    "trade_id": str(trade_id),
                    "price": str(price),
                    "quantity": str(quantity),
                    "side": "sell" if bool(is_buyer_maker) else "buy",
                    "event_time": event_time,
                }
                handle.write(json.dumps(tick) + "\n")
                handle.flush()
                logger.info("tick %s %s@%s", symbol, quantity, price)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live tick bridge to JSONL for quant-terminal-web")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--output",
        default=str(project_root() / "data" / "live" / "ticks.jsonl"),
        help="JSONL output path (TERMINAL_TICKS_JSONL)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(stream_binance_trades(args.symbol.upper(), Path(args.output)))


if __name__ == "__main__":
    main()
