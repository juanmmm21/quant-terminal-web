from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from quant_terminal_api.app import create_app
from quant_terminal_api.config import TerminalSettings


def test_public_paper_is_read_only_and_reports_liveness(
    settings: TerminalSettings, tmp_path: Path
) -> None:
    settings.paper_dir = tmp_path / "paper"
    settings.paper_dir.mkdir()
    client = TestClient(create_app(settings))
    assert client.get("/api/v1/public/paper").status_code == 404
    (settings.paper_dir / "comparison.json").write_text(
        json.dumps({"strategy": "rsi_mean_reversion", "paper": {"pnl": "1.5"},
                    "backtest": {"pnl": "2.0"}}),
        encoding="utf-8",
    )
    (settings.paper_dir / "heartbeat.json").write_text(
        json.dumps({"at": (datetime.now(tz=UTC) - timedelta(seconds=5)).isoformat()}),
        encoding="utf-8",
    )
    body = client.get("/api/v1/public/paper").json()
    assert body["trader_alive"] is True and body["paper"]["pnl"] == "1.5"
    assert client.post("/api/v1/public/paper").status_code == 405
    assert client.delete("/api/v1/public/paper").status_code == 405
