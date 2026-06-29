from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from quant_terminal_api.app import create_app
from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.models import BotStatus
from quant_terminal_api.readers import (
    AuditReader,
    EquityReader,
    LakehouseCandlesReader,
    MetricsReader,
    TradesReader,
)


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
    return TerminalSettings(
        audit_db_path=samples_dir / "audit.db",
        metrics_path=samples_dir / "metrics.json",
        equity_path=samples_dir / "equity.json",
        trades_path=samples_dir / "trades.jsonl",
        lakehouse_root=lakehouse_dir,
        lakehouse_duckdb=lakehouse_dir / "catalog.duckdb",
        ticks_jsonl_path=ticks_path,
        bot_state_path=samples_dir / "bot_state.json",
    ).resolve_paths()


@pytest.fixture
def client(settings: TerminalSettings) -> TestClient:
    return TestClient(create_app(settings))


def test_metrics_reader_loads_decimal_strings(settings: TerminalSettings) -> None:
    metrics = MetricsReader(settings.metrics_path).load()
    assert metrics.symbol == "BTCUSDT"
    assert metrics.sharpe_ratio == "1.42"
    assert metrics.trade_count == 2


def test_equity_reader_loads_curve(settings: TerminalSettings) -> None:
    equity = EquityReader(settings.equity_path).load()
    assert equity.symbol == "BTCUSDT"
    assert len(equity.points) == 6
    assert equity.initial_capital == "10000.00"
    assert equity.current_capital == "10330.00"


def test_lakehouse_candles_reader(settings: TerminalSettings) -> None:
    reader = LakehouseCandlesReader(
        settings.lakehouse_root,
        settings.lakehouse_duckdb,
        symbol="BTCUSDT",
        timeframe="1h",
        limit=10,
    )
    candles = reader.load()
    assert candles.last_price == "60152.00"
    assert len(candles.candles) == 2


def test_trades_reader(settings: TerminalSettings) -> None:
    trades = TradesReader(settings.trades_path).load()
    assert trades.count == 4
    assert trades.closed_round_trips == 2


def test_audit_reader_filters(settings: TerminalSettings) -> None:
    reader = AuditReader(settings.audit_db_path)
    all_events = reader.fetch_events(limit=50)
    assert len(all_events) == 7
    errors = reader.fetch_events(limit=10, event_type="system_error")
    assert len(errors) == 1
    assert errors[0].severity == "warning"


def test_bot_state_persists(settings: TerminalSettings) -> None:
    store = BotStateStore(settings.bot_state_path)
    store.set_paused("test pause")
    reloaded = BotStateStore(settings.bot_state_path)
    assert reloaded.status == BotStatus.PAUSED
    assert reloaded.message == "test pause"


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data_mode"] == "live"


def test_bot_panic_flow(client: TestClient) -> None:
    pause = client.post("/api/v1/bot/pause")
    assert pause.status_code == 200
    assert pause.json()["status"] == "paused"

    panic = client.post("/api/v1/bot/panic", json={"reason": "test emergency"})
    assert panic.status_code == 200
    assert panic.json()["status"] == "panic"

    resume = client.post("/api/v1/bot/resume")
    assert resume.status_code == 409

    reset = client.post("/api/v1/bot/reset")
    assert reset.status_code == 200
    assert reset.json()["status"] == "running"


def test_metrics_and_equity_endpoints(client: TestClient) -> None:
    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["profit_factor"] == "1.85"

    equity = client.get("/api/v1/equity-curve")
    assert equity.status_code == 200
    assert len(equity.json()["points"]) == 6
    assert equity.json()["current_capital"] == "10330.00"

    candles = client.get("/api/v1/market/candles")
    assert candles.status_code == 200
    assert candles.json()["last_price"] == "60152.00"

    trades = client.get("/api/v1/trades")
    assert trades.status_code == 200
    assert trades.json()["count"] == 4

    summary = client.get("/api/v1/summary")
    assert summary.status_code == 200
    assert summary.json()["trade_count"] == 2
    assert summary.json()["data_mode"] == "live"


def test_audit_events_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/audit/events?limit=3")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert len(body["events"]) == 3
