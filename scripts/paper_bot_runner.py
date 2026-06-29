#!/usr/bin/env python3
"""
Bot en paper trading: re-ejecuta el pipeline del ecosistema cuando hay ticks nuevos.

Respeta bot_state.json (pause/panic) escrito por la API del terminal.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ecosystem_tools import project_root, resolve_ticks_source
from run_ecosystem_pipeline import run_pipeline

logger = logging.getLogger(__name__)


def read_bot_status(state_path: Path) -> str:
    if not state_path.exists():
        return "running"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "running"
    if isinstance(payload, dict) and isinstance(payload.get("status"), str):
        return payload["status"]
    return "running"


def tick_file_size(path: Path) -> int:
    if not path.exists():
        return 0
    return path.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper bot runner for quant-terminal-web")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--strategy", default="rsi_mean_reversion")
    parser.add_argument("--interval-seconds", type=int, default=120)
    parser.add_argument("--ticks", default=None)
    parser.add_argument(
        "--bot-state",
        default=str(project_root() / "data" / "ecosystem" / "bot_state.json"),
    )
    parser.add_argument("--run-once", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ticks_path = Path(args.ticks).resolve() if args.ticks else resolve_ticks_source()
    state_path = Path(args.bot_state).resolve()
    last_size = tick_file_size(ticks_path)

    while True:
        status = read_bot_status(state_path)
        if status == "panic":
            logger.warning("bot in panic — pipeline halted until manual reset")
        elif status == "paused":
            logger.info("bot paused — skipping pipeline run")
        else:
            current_size = tick_file_size(ticks_path)
            if current_size != last_size or args.run_once:
                logger.info("tick file changed (%s → %s bytes), running pipeline", last_size, current_size)
                try:
                    run_pipeline(
                        symbol=args.symbol.upper(),
                        timeframe=args.timeframe,
                        strategy=args.strategy,
                        ticks_path=ticks_path,
                        skip_lakehouse=False,
                    )
                    last_size = current_size
                except Exception as exc:
                    logger.error("pipeline run failed: %s", exc)
            else:
                logger.debug("no new ticks — skipping pipeline")

        if args.run_once:
            break
        time.sleep(max(args.interval_seconds, 10))


if __name__ == "__main__":
    main()
