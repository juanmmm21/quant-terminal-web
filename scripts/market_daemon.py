#!/usr/bin/env python3
"""
Daemon de mercado: ticks live → lakehouse → análisis periódico.

Respeta bot_state.json (pause/panic detiene el análisis).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from analysis_engine import run_all_timeframes
from ecosystem_tools import project_root, resolve_cli, run_cli

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


def ingest_ticks(ticks_path: Path, lake_root: Path, *, symbol: str) -> None:
    if not ticks_path.exists() or ticks_path.stat().st_size == 0:
        return
    cli = resolve_cli("market-data-lakehouse")
    run_cli(
        [
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
    )


def start_tick_bridge(symbol: str, output: Path) -> subprocess.Popen[str]:
  cmd = [sys.executable, str(_SCRIPTS_DIR / "tick_bridge.py"), "--symbol", symbol, "--output", str(output)]
  logger.info("starting tick bridge: %s", " ".join(cmd))
  return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Market data + analysis daemon")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--ingest-interval", type=int, default=45)
    parser.add_argument("--analysis-interval", type=int, default=90)
    parser.add_argument("--no-tick-bridge", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = project_root()
    ticks_path = root / "data" / "live" / "ticks.jsonl"
    lake_root = root / "data" / "lake"
    state_path = root / "data" / "runtime" / "bot_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if not state_path.exists():
        state_path.write_text(
            json.dumps({"status": "running", "updated_at": time.time(), "message": "daemon started"})
            + "\n",
            encoding="utf-8",
        )

    bridge_proc: subprocess.Popen[str] | None = None
    if not args.no_tick_bridge:
        bridge_proc = start_tick_bridge(args.symbol.upper(), ticks_path)

    last_tick_size = tick_file_size(ticks_path)
    last_ingest = 0.0
    last_analysis = 0.0

    try:
        while True:
            now = time.time()
            status = read_bot_status(state_path)
            current_tick_size = tick_file_size(ticks_path)

            if status == "panic":
                logger.warning("bot panic — analysis halted")
            elif status == "paused":
                logger.info("bot paused — skipping analysis cycle")
            else:
                if current_tick_size != last_tick_size and now - last_ingest >= args.ingest_interval:
                    try:
                        ingest_ticks(ticks_path, lake_root, symbol=args.symbol.upper())
                        last_tick_size = current_tick_size
                        last_ingest = now
                    except Exception as exc:
                        logger.error("lakehouse ingest failed: %s", exc)

                if now - last_analysis >= args.analysis_interval:
                    try:
                        run_all_timeframes(symbol=args.symbol.upper())
                        last_analysis = now
                    except Exception as exc:
                        logger.error("analysis cycle failed: %s", exc)

            if bridge_proc is not None and bridge_proc.poll() is not None:
                logger.error("tick bridge exited — restarting")
                bridge_proc = start_tick_bridge(args.symbol.upper(), ticks_path)

            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("daemon stopping")
    finally:
        if bridge_proc is not None and bridge_proc.poll() is None:
            bridge_proc.terminate()


if __name__ == "__main__":
    main()
