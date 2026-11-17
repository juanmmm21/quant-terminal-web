from __future__ import annotations

from conftest import ADMIN
from fastapi.testclient import TestClient

from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.models import BotStatus
from quant_terminal_api.readers import (
    AnalysisCacheReader,
    AuditReader,
    EquityReader,
    LakehouseCandlesReader,
    MetricsReader,
    TradesReader,
)


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


def test_analysis_reader(settings: TerminalSettings) -> None:
    reader = AnalysisCacheReader(settings.runtime_dir, symbol="BTCUSDT")
    snapshot = reader.load_snapshot("1h")
    assert snapshot.recommendation.verdict == "hold"
    assert snapshot.training.bars_analyzed == 100


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
    pause = client.post("/api/v1/bot/pause", headers=ADMIN)
    assert pause.status_code == 200
    assert pause.json()["status"] == "paused"

    panic = client.post(
        "/api/v1/bot/panic", json={"reason": "test emergency"}, headers=ADMIN
    )
    assert panic.status_code == 200
    assert panic.json()["status"] == "panic"

    resume = client.post("/api/v1/bot/resume", headers=ADMIN)
    assert resume.status_code == 409

    reset = client.post("/api/v1/bot/reset", headers=ADMIN)
    assert reset.status_code == 200
    assert reset.json()["status"] == "running"


def test_metrics_and_equity_endpoints(client: TestClient) -> None:
    candles = client.get("/api/v1/market/candles?timeframe=1h")
    assert candles.status_code == 200
    assert candles.json()["last_price"] == "60152.00"

    analysis = client.get("/api/v1/analysis/snapshot?timeframe=1h")
    assert analysis.status_code == 200
    assert analysis.json()["recommendation"]["verdict"] == "hold"

    summary = client.get("/api/v1/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["recommendation_verdict"] == "hold"
    assert body["data_mode"] == "live"


def test_audit_events_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/audit/events?limit=3")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert len(body["events"]) == 3


def test_ecosystem_status_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/ecosystem/status")
    assert response.status_code == 200
    body = response.json()
    assert body["lakehouse_ready"] is True
    assert body["analysis_ready"] is True
    assert "modules" in body
