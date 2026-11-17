from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from analysis_fixture import write_sample_analysis
from fastapi.testclient import TestClient
from pydantic import SecretStr

from quant_terminal_api.app import create_app
from quant_terminal_api.config import TerminalSettings

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

ADMIN_TOKEN = "test-admin-token-not-a-secret"


def _seed_lakehouse_parquet(
    lake_root: Path,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
) -> None:
    parquet_path = (
        lake_root
        / "binance"
        / symbol
        / timeframe
        / "year=2026"
        / "month=06"
        / "day=29"
        / "candles.parquet"
    )
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    path_sql = str(parquet_path).replace("'", "''")
    connection = duckdb.connect()
    try:
        connection.execute(
            f"""
            COPY (
                SELECT
                    'binance' AS exchange,
                    '{symbol}' AS symbol,
                    '{timeframe}' AS timeframe,
                    TIMESTAMPTZ '2026-06-29 08:00:00+00' AS open_time,
                    TIMESTAMPTZ '2026-06-29 09:00:00+00' AS close_time,
                    '60000.00' AS open,
                    '60100.00' AS high,
                    '59900.00' AS low,
                    '60050.00' AS close,
                    '100.5' AS volume,
                    CAST(10 AS BIGINT) AS trade_count
                UNION ALL
                SELECT
                    'binance',
                    '{symbol}',
                    '{timeframe}',
                    TIMESTAMPTZ '2026-06-29 09:00:00+00',
                    TIMESTAMPTZ '2026-06-29 10:00:00+00',
                    '60050.00',
                    '60200.00',
                    '60000.00',
                    '60152.00',
                    '120.2',
                    CAST(12 AS BIGINT)
            ) TO '{path_sql}' (FORMAT PARQUET)
            """
        )
    finally:
        connection.close()


@pytest.fixture
def samples_dir(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "samples"
    target = tmp_path / "samples"
    target.mkdir()
    sample_files = (
        "metrics.json",
        "equity.json",
        "trades.jsonl",
        "audit_events.jsonl",
    )
    for name in sample_files:
        (target / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")

    db_path = target / "audit.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE audit_events (
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
    )
    recorded_at = datetime.now(tz=UTC).isoformat()
    for line in (target / "audit_events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        connection.execute(
            """
            INSERT INTO audit_events (
                event_id, event_type, symbol, correlation_id,
                occurred_at, recorded_at, severity, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["event_type"],
                event["symbol"],
                event["correlation_id"],
                event["occurred_at"],
                recorded_at,
                event["severity"],
                json.dumps(event["payload"]),
            ),
        )
    connection.commit()
    connection.close()
    return target


@pytest.fixture
def lakehouse_dir(tmp_path: Path) -> Path:
    lake_root = tmp_path / "lake"
    _seed_lakehouse_parquet(lake_root)
    return lake_root


@pytest.fixture
def settings(samples_dir: Path, lakehouse_dir: Path, tmp_path: Path) -> TerminalSettings:
    ticks_path = tmp_path / "live" / "ticks.jsonl"
    ticks_path.parent.mkdir(parents=True)
    ticks_path.write_text(
        json.dumps(
            {
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "trade_id": "live-1",
                "price": "60152.00",
                "quantity": "0.01",
                "side": "buy",
                "event_time": datetime.now(tz=UTC).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    write_sample_analysis(runtime_dir / "analysis_1h.json", timeframe="1h")
    bot_state = runtime_dir / "bot_state.json"
    bot_state.write_text(
        json.dumps(
            {
                "status": "running",
                "updated_at": datetime.now(tz=UTC).isoformat(),
                "message": "ok",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return TerminalSettings(
        audit_db_path=samples_dir / "audit.db",
        metrics_path=samples_dir / "metrics.json",
        equity_path=samples_dir / "equity.json",
        trades_path=samples_dir / "trades.jsonl",
        lakehouse_root=lakehouse_dir,
        lakehouse_duckdb=lakehouse_dir / "catalog.duckdb",
        ticks_jsonl_path=ticks_path,
        bot_state_path=bot_state,
        runtime_dir=runtime_dir,
        devices_path=runtime_dir / "devices.json",
        promotion_path=runtime_dir / "paper_promotion.json",
        admin_token=SecretStr(ADMIN_TOKEN),
    ).resolve_paths()


@pytest.fixture
def client(settings: TerminalSettings) -> TestClient:
    return TestClient(create_app(settings))




ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
