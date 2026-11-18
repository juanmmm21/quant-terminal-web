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


class TickTail:
    """Reads only the bytes appended since the last call; follows size-based rotation.

    websocket-feed-handler --rotate-bytes renames the full file to ``<name>.1`` and starts a new
    one. When the inode changes, the rest of the rotated file is read first, then the new file
    from its start, so no complete line is lost.
    """

    def __init__(self, path: Path, *, from_end: bool = True) -> None:
        self.path = path
        self.offset = path.stat().st_size if from_end and path.exists() else 0
        self.inode = path.stat().st_ino if path.exists() else None

    def read_new(self) -> list[str]:
        if not self.path.exists():
            return []
        stat = self.path.stat()
        lines: list[str] = []
        if self.inode is not None and stat.st_ino != self.inode:
            rotated = self.path.with_name(self.path.name + ".1")
            if rotated.exists() and rotated.stat().st_ino == self.inode:
                lines += self._read(rotated, self.offset)[0]
            self.offset = 0
        elif stat.st_size < self.offset:  # truncated in place
            self.offset = 0
        self.inode = stat.st_ino
        new_lines, self.offset = self._read(self.path, self.offset)
        return lines + new_lines

    @staticmethod
    def _read(path: Path, offset: int) -> tuple[list[str], int]:
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
        complete = chunk[: chunk.rfind(b"\n") + 1]  # keep a half-written last line for later
        text = complete.decode("utf-8", errors="replace")
        return [line for line in text.splitlines() if line.strip()], offset + len(complete)


def write_tick_delta(tail: TickTail, staging: Path) -> int:
    """Write the ticks appended since the last call to ``staging``; returns how many."""
    lines = tail.read_new()
    if not lines:
        return 0
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_text("\n".join(lines) + "\n", encoding="utf-8")
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

    tail = TickTail(ticks_path)

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
                    count = write_tick_delta(tail, tick_delta_path)
                    if count:
                        try:
                            ingest_ticks(tick_delta_path, lake_root, symbol=symbol)
                            last_ingest = now
                            ingested = True
                            logger.info("ingested %s live ticks (offset=%s)", count, tail.offset)
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
