"""``quant-paper-trader``: the 24/7 paper-trading process (testnet by default).

Runs ``PaperTrader.step`` every ``TERMINAL_PAPER_INTERVAL_SECONDS`` until SIGTERM/SIGINT, writes
``data/paper/heartbeat.json`` after every step (the container health check reads it) and never
exits on a failed step: errors are logged and the next step retries. Restarts are handled by the
supervisor (``restart: unless-stopped`` in docker compose); state survives them on disk.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.paper.engine import (
    CapsRiskGate,
    CliRiskGate,
    CombinedRiskGate,
    PaperTrader,
    TraderConfig,
    read_json,
)
from quant_terminal_api.paper.journal import PaperJournal
from quant_terminal_api.paper.market import read_market
from quant_terminal_api.paper.venue import ExecutionVenue, GatewayCliVenue, SimulatedVenue

logger = logging.getLogger(__name__)


def build_trader(settings: TerminalSettings, *, venue_name: str) -> PaperTrader:
    journal = PaperJournal(settings.paper_dir, initial_cash=Decimal(settings.paper_initial_cash))
    venue: ExecutionVenue
    if venue_name == "testnet":
        venue = GatewayCliVenue()
    elif venue_name == "simulated":
        venue = SimulatedVenue()
    else:
        raise ValueError(f"unknown venue {venue_name!r} (testnet | simulated)")

    def market() -> Any:
        view = read_market(settings.ticks_jsonl_path, settings.feed_status_path)
        if isinstance(venue, SimulatedVenue) and view.price is not None:
            venue.price = view.price  # simulated fills at the live market price
        return view

    def bot_status() -> str:
        payload = read_json(settings.bot_state_path) or {}
        return str(payload.get("status", "running"))

    def promotion() -> dict[str, Any] | None:
        payload = read_json(settings.promotion_path)
        return payload if payload and payload.get("active") else None

    def recommendation(timeframe: str) -> dict[str, Any] | None:
        analysis = read_json(settings.runtime_dir / f"analysis_{timeframe}.json")
        rec = (analysis or {}).get("recommendation")
        return rec if isinstance(rec, dict) else None

    config = TraderConfig(
        symbol=settings.candle_symbol,
        quantity=Decimal(settings.paper_quantity),
        max_position=Decimal(settings.paper_max_position),
        max_order_notional=Decimal(settings.paper_max_order_notional),
    )
    risk = CombinedRiskGate(
        CapsRiskGate(config.max_position, config.max_order_notional),
        CliRiskGate(settings.paper_dir / "work", journal),
    )
    return PaperTrader(config=config, journal=journal, venue=venue, market=market,
                       bot_status=bot_status, promotion=promotion,
                       recommendation=recommendation, risk=risk)


def run_forever(trader: PaperTrader, *, interval: float, heartbeat: Path,
                stop: threading.Event, max_steps: int | None = None) -> None:
    steps = 0
    while not stop.is_set():
        started = datetime.now(tz=UTC)
        try:
            result = trader.step()
            outcome = {"action": result.action, "detail": result.detail}
        except Exception as exc:  # a bad step must never kill the 24/7 loop
            logger.exception("paper step failed")
            outcome = {"action": "error", "detail": str(exc)}
        state = trader.journal.state
        payload = {
            "at": started.isoformat(), "pid": os.getpid(), "venue": trader.venue.name,
            **outcome, "position": state.position, "cash": state.cash,
            "pending": list(state.pending), "kill_pending": state.kill_pending,
            "halted_reason": state.halted_reason,
        }
        tmp = heartbeat.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        os.replace(tmp, heartbeat)
        logger.info("step %s: %s", outcome["action"], outcome["detail"])
        steps += 1
        if max_steps is not None and steps >= max_steps:
            return
        stop.wait(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="24/7 paper trader (Binance testnet)")
    parser.add_argument("--venue", default=os.environ.get("TERMINAL_PAPER_VENUE", "testnet"),
                        choices=["testnet", "simulated"])
    parser.add_argument("--interval-seconds", type=float,
                        default=float(os.environ.get("TERMINAL_PAPER_INTERVAL_SECONDS", "10")))
    parser.add_argument("--max-steps", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    settings = TerminalSettings().resolve_paths()
    trader = build_trader(settings, venue_name=args.venue)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    logger.info("paper trader started venue=%s symbol=%s", args.venue, settings.candle_symbol)
    run_forever(trader, interval=args.interval_seconds,
                heartbeat=settings.paper_dir / "heartbeat.json", stop=stop,
                max_steps=args.max_steps)
    logger.info("paper trader stopped")


if __name__ == "__main__":
    main()
