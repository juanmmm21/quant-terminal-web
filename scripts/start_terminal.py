#!/usr/bin/env python3
"""
Arranque con un solo comando: histórico + ticks live + análisis + API + UI.

Uso:
  python3 scripts/start_terminal.py
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _resolve_api_cmd() -> list[str]:
    api = shutil.which("quant-terminal-api")
    if api:
        return [api]
    backend_venv = _ROOT / "backend" / ".venv" / "bin" / "quant-terminal-api"
    if backend_venv.exists():
        return [str(backend_venv)]
    return [sys.executable, "-m", "quant_terminal_api"]


def _lakehouse_ready() -> bool:
    lake = _ROOT / "data" / "lake"
    return lake.exists() and any(lake.rglob("candles.parquet"))


def _bootstrap_historical() -> None:
    bootstrap = _SCRIPTS_DIR / "bootstrap_market_data.py"
    logging.info("bootstrapping historical market data...")
    subprocess.run([sys.executable, str(bootstrap)], check=True, cwd=_ROOT)


def _ensure_websockets() -> None:
    try:
        import websockets  # noqa: F401
    except ImportError:
        logging.info("installing websockets for live ticks...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "websockets"],
            check=False,
        )


def _spawn(cmd: list[str], *, cwd: Path, name: str) -> subprocess.Popen[str]:
    logging.info("starting %s: %s", name, " ".join(cmd))
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Start full quant-terminal-web stack")
    parser.add_argument("--skip-bootstrap", action="store_true")
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.skip_bootstrap and not _lakehouse_ready():
        _bootstrap_historical()

    _ensure_websockets()

    children: list[subprocess.Popen[str]] = []
    children.append(
        _spawn(
            [sys.executable, str(_SCRIPTS_DIR / "market_daemon.py")],
            cwd=_ROOT,
            name="market-daemon",
        )
    )

    api_cmd = _resolve_api_cmd() + ["--host", "127.0.0.1", "--port", str(args.port)]
    children.append(_spawn(api_cmd, cwd=_ROOT / "backend", name="api"))

    if not args.skip_ui:
        npm = shutil.which("npm")
        if npm is None:
            raise SystemExit("npm not found — install Node.js 20+")
        children.append(_spawn([npm, "run", "dev"], cwd=_ROOT, name="frontend"))

    def shutdown(*_args: object) -> None:
        for proc in children:
            if proc.poll() is None:
                proc.terminate()
        time.sleep(0.5)
        for proc in children:
            if proc.poll() is None:
                proc.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("\nquant-terminal-web")
    print(f"  API:  http://127.0.0.1:{args.port}")
    print("  UI:   http://localhost:5173")
    print("  Ctrl+C para detener todo\n")

    try:
        while True:
            for proc in children:
                if proc.poll() is not None:
                    output = proc.stdout.read() if proc.stdout else ""
                    logging.error("process exited: %s\n%s", proc.args, output)
                    shutdown()
            time.sleep(2)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
