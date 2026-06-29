#!/usr/bin/env python3
"""
Daemon de mercado: ticks live → lakehouse → análisis periódico.

Ingesta incremental de ticks nuevos y re-analiza tras cada ingesta.
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


def write_tick_delta(source: Path, staging: Path, *, line_offset: int) -> int:
    """Escribe ticks nuevos desde line_offset. Devuelve el nuevo offset."""
    if not source.exists():
        return line_offset
    lines = source.read_text(encoding="utf-8").splitlines()
    if len(lines) <= line_offset:
        return line_offset
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_text("\n".join(lines[line_offset:]) + "\n", encoding="utf-8")
    return len(lines)


def start_tick_bridge(symbol: str, output: Path) -> subprocess.Popen[bytes]:
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "tick_bridge.py"),
        "--symbol",
        symbol,
        "--output",
        str(output),
    ]
    logger.info("starting tick bridge: %s", " ".join(cmd))
    return subprocess.Popen(cmd)


def run_analysis_cycle(symbol: str) -> None:
    run_all_timeframes(symbol=symbol)


def main() -> None:
    parser = argparse.ArgumentParser(description="Market data + analysis daemon")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--ingest-interval", type=int, default=10)
    parser.add_argument("--analysis-interval", type=int, default=45)
    parser.add_argument("--no-tick-bridge", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = project_root()
    ticks_path = root / "data" / "live" / "ticks.jsonl"
    tick_delta_path = root / "data" / "runtime" / "ticks_delta.jsonl"
    lake_root = root / "data" / "lake"
    state_path = root / "data" / "runtime" / "bot_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if not state_path.exists():
        state_path.write_text(
            json.dumps({"status": "running", "updated_at": time.time(), "message": "daemon started"})
            + "\n",
            encoding="utf-8",
        )

    symbol = args.symbol.upper()
    bridge_proc: subprocess.Popen[bytes] | None = None
    if not args.no_tick_bridge:
        bridge_proc = start_tick_bridge(symbol, ticks_path)

    tick_line_offset = 0
    if ticks_path.exists():
        tick_line_offset = len(ticks_path.read_text(encoding="utf-8").splitlines())

    last_ingest = 0.0
    last_analysis = 0.0

    try:
        logger.info("initial analysis cycle")
        run_analysis_cycle(symbol)
        last_analysis = time.time()

        while True:
            now = time.time()
            status = read_bot_status(state_path)

            if status == "panic":
                logger.warning("bot panic — analysis halted")
            elif status == "paused":
                logger.debug("bot paused — skipping cycle")
            else:
                ingested = False
                if now - last_ingest >= args.ingest_interval:
                    new_offset = write_tick_delta(
                        ticks_path,
                        tick_delta_path,
                        line_offset=tick_line_offset,
                    )
                    if new_offset > tick_line_offset:
                        try:
                            ingest_ticks(tick_delta_path, lake_root, symbol=symbol)
                            tick_line_offset = new_offset
                            last_ingest = now
                            ingested = True
                            logger.info("ingested live ticks (offset=%s)", tick_line_offset)
                        except Exception as exc:
                            logger.error("lakehouse ingest failed: %s", exc)

                if ingested or now - last_analysis >= args.analysis_interval:
                    try:
                        run_analysis_cycle(symbol)
                        last_analysis = now
                    except Exception as exc:
                        logger.error("analysis cycle failed: %s", exc)

            if bridge_proc is not None and bridge_proc.poll() is not None:
                logger.error("tick bridge exited — restarting")
                bridge_proc = start_tick_bridge(symbol, ticks_path)

            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("daemon stopping")
    finally:
        if bridge_proc is not None and bridge_proc.poll() is None:
            bridge_proc.terminate()


if __name__ == "__main__":
    main()
