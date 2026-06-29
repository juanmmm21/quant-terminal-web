from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quant_terminal_api.app import create_app
from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.models import BotStatus
from quant_terminal_api.readers import AuditReader, EquityReader, MetricsReader


@pytest.fixture
def samples_dir(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "samples"
    target = tmp_path / "samples"
    target.mkdir()
    for name in ("metrics.json", "equity.json", "audit_events.jsonl"):
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
def settings(samples_dir: Path) -> TerminalSettings:
    return TerminalSettings(
        audit_db_path=samples_dir / "audit.db",
        metrics_path=samples_dir / "metrics.json",
        equity_path=samples_dir / "equity.json",
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
    symbol, points = EquityReader(settings.equity_path).load()
    assert symbol == "BTCUSDT"
    assert len(points) == 10
    assert points[0].equity == "10000.00"


def test_audit_reader_filters(settings: TerminalSettings) -> None:
    reader = AuditReader(settings.audit_db_path)
    all_events = reader.fetch_events(limit=50)
    assert len(all_events) == 7
    errors = reader.fetch_events(limit=10, event_type="system_error")
    assert len(errors) == 1
    assert errors[0].severity == "error"


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


def test_bot_panic_flow(client: TestClient) -> None:
    pause = client.post("/api/v1/bot/pause")
    assert pause.status_code == 200
    assert pause.json()["status"] == "paused"

    panic = client.post("/api/v1/bot/panic", json={"reason": "test emergency"})
    assert panic.status_code == 200
    assert panic.json()["status"] == "panic"

    resume = client.post("/api/v1/bot/resume")
    assert resume.status_code == 409


def test_metrics_and_equity_endpoints(client: TestClient) -> None:
    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["profit_factor"] == "1.85"

    equity = client.get("/api/v1/equity-curve")
    assert equity.status_code == 200
    assert len(equity.json()["points"]) == 10


def test_audit_events_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/audit/events?limit=3")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert len(body["events"]) == 3
