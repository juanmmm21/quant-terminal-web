#!/usr/bin/env python3
"""
Arranque con un solo comando: histórico + ticks live + análisis + API + UI.

Uso (desde la raíz del repo):
  python3 scripts/start_terminal.py
  npm start
"""

from __future__ import annotations

import argparse
import logging
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPTS_DIR.parent
_BACKEND = _ROOT / "backend"
_VENV_PYTHON = _BACKEND / ".venv" / "bin" / "python3"


def _venv_python() -> Path:
    if _VENV_PYTHON.exists():
        return _VENV_PYTHON
    return Path(sys.executable)


def _resolve_api_cmd() -> list[str]:
    venv_api = _BACKEND / ".venv" / "bin" / "quant-terminal-api"
    if venv_api.exists():
        return [str(venv_api)]
    found = shutil.which("quant-terminal-api")
    if found:
        return [found]
    return [str(_venv_python()), "-m", "quant_terminal_api"]


def _lakehouse_ready() -> bool:
    lake = _ROOT / "data" / "lake"
    return lake.exists() and any(lake.rglob("candles.parquet"))


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _api_health_ok(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _ensure_backend_venv() -> None:
    if _VENV_PYTHON.exists():
        return
    logging.info("creating backend virtualenv at backend/.venv ...")
    subprocess.run([sys.executable, "-m", "venv", str(_BACKEND / ".venv")], check=True, cwd=_BACKEND)


def _pip_install(*packages: str) -> None:
    python = _venv_python()
    logging.info("installing in venv: %s", ", ".join(packages))
    subprocess.run(
        [str(python), "-m", "pip", "install", *packages],
        check=True,
        cwd=_BACKEND,
    )


def _ensure_backend_deps() -> None:
    _ensure_backend_venv()
    marker = _BACKEND / ".venv" / ".terminal_stack_ready"
    if marker.exists():
        _ensure_websockets()
        return
    logging.info("installing backend package (first run)...")
    subprocess.run(
        [str(_venv_python()), "-m", "pip", "install", "-e", ".[dev]"],
        check=True,
        cwd=_BACKEND,
    )
    _ensure_websockets()
    marker.write_text("ok\n", encoding="utf-8")


def _ensure_websockets() -> None:
    python = _venv_python()
    check = subprocess.run(
        [str(python), "-c", "import websockets"],
        capture_output=True,
    )
    if check.returncode == 0:
        return
    _pip_install("websockets")


def _lakehouse_1h_bars() -> int:
    lake = _ROOT / "data" / "lake"
    if not lake.exists():
        return 0
    parquet_files = list(lake.rglob("candles.parquet"))
    if not parquet_files:
        return 0
    import duckdb

    paths_sql = ", ".join("'" + str(path).replace("'", "''") + "'" for path in parquet_files)
    connection = duckdb.connect()
    try:
        row = connection.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet([{paths_sql}], union_by_name=true)
            WHERE symbol = 'BTCUSDT' AND timeframe = '1h'
            """
        ).fetchone()
    finally:
        connection.close()
    return int(row[0]) if row else 0


def _lakehouse_needs_bootstrap(*, min_1h_bars: int = 2000) -> bool:
    if not _lakehouse_ready():
        return True
    return _lakehouse_1h_bars() < min_1h_bars


def _bootstrap_historical(*, days_1m: int = 60, days_1h: int = 365) -> None:
    bootstrap = _SCRIPTS_DIR / "bootstrap_market_data.py"
    logging.info(
        "bootstrapping historical market data (1m=%s days, 1h=%s days)...",
        days_1m,
        days_1h,
    )
    subprocess.run(
        [
            str(_venv_python()),
            str(bootstrap),
            "--days-1m",
            str(days_1m),
            "--days-1h",
            str(days_1h),
        ],
        check=True,
        cwd=_ROOT,
    )


_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def _ensure_runtime_audit_db() -> None:
    db_path = _ROOT / "data" / "runtime" / "audit.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(_AUDIT_SCHEMA)
        connection.commit()
    finally:
        connection.close()


def _spawn(cmd: list[str], *, cwd: Path, name: str) -> subprocess.Popen[bytes]:
    logging.info("starting %s: %s", name, " ".join(cmd))
    # Heredar stdout/stderr: capturar en PIPE bloquea Vite/npm cuando el buffer se llena.
    return subprocess.Popen(cmd, cwd=cwd)


def _resolve_api_port(requested: int) -> tuple[int, bool]:
    """
    Returns (port, should_spawn_api).
    Reuses an existing quant-terminal-api on the requested port when healthy.
    """
    if _port_is_free("127.0.0.1", requested):
        return requested, True
    if _api_health_ok(requested):
        logging.info(
            "API already running on port %s — reusing existing instance",
            requested,
        )
        return requested, False
    for candidate in range(requested + 1, requested + 10):
        if _port_is_free("127.0.0.1", candidate):
            logging.warning(
                "port %s is busy (not our API) — using %s instead",
                requested,
                candidate,
            )
            return candidate, True
    raise SystemExit(
        f"ports {requested}-{requested + 9} are busy. "
        "Stop other processes or run: lsof -i :8000"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Start full quant-terminal-web stack")
    parser.add_argument("--skip-bootstrap", action="store_true")
    parser.add_argument(
        "--refresh-history",
        action="store_true",
        help="re-download Binance history even if lakehouse already exists",
    )
    parser.add_argument("--history-days-1m", type=int, default=90)
    parser.add_argument("--history-days-1h", type=int, default=730)
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    _ensure_backend_deps()
    _ensure_runtime_audit_db()

    if not args.skip_bootstrap and (
        args.refresh_history or _lakehouse_needs_bootstrap(min_1h_bars=2000)
    ):
        _bootstrap_historical(days_1m=args.history_days_1m, days_1h=args.history_days_1h)

    api_port, spawn_api = _resolve_api_port(args.port)
    python = str(_venv_python())

    children: list[subprocess.Popen[bytes]] = []
    children.append(
        _spawn(
            [python, str(_SCRIPTS_DIR / "market_daemon.py")],
            cwd=_ROOT,
            name="market-daemon",
        )
    )

    if spawn_api:
        api_cmd = _resolve_api_cmd() + ["--host", "127.0.0.1", "--port", str(api_port)]
        children.append(_spawn(api_cmd, cwd=_BACKEND, name="api"))

    if not args.skip_ui:
        frontend_node_modules = _ROOT / "frontend" / "node_modules"
        if not frontend_node_modules.exists():
            npm = shutil.which("npm")
            if npm is None:
                raise SystemExit("npm not found — install Node.js 20+")
            logging.info("installing frontend dependencies (first run)...")
            subprocess.run([npm, "install"], check=True, cwd=_ROOT / "frontend")
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
    print(f"  API:  http://127.0.0.1:{api_port}/api/v1/health")
    print("  UI:   http://localhost:5173  ← abre esta URL en el navegador")
    if not spawn_api:
        print("  (API ya estaba en marcha — no se lanzó otra instancia)")
    print("  Ctrl+C para detener procesos iniciados por este script\n")

    try:
        while True:
            for proc in children:
                if proc.poll() is not None:
                    logging.error("process exited: %s (code %s)", proc.args, proc.returncode)
                    shutdown()
            time.sleep(2)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
