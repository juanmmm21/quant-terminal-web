from __future__ import annotations

import json
import shutil
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.paper.engine import CliRiskGate, StepResult
from quant_terminal_api.paper.journal import PaperJournal
from quant_terminal_api.paper.runner import build_trader, run_forever
from quant_terminal_api.paper.venue import OrderIntent


def test_runner_writes_heartbeat_and_survives_a_failing_step(
    settings: TerminalSettings, tmp_path: Path
) -> None:
    settings.paper_dir = tmp_path / "paper"
    settings.paper_dir.mkdir()
    trader = build_trader(settings, venue_name="simulated")
    calls = {"n": 0}
    original = trader.step

    def flaky() -> StepResult:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("disk hiccup")
        return original()

    trader.step = flaky  # type: ignore[method-assign]
    heartbeat = settings.paper_dir / "heartbeat.json"
    run_forever(trader, interval=0, heartbeat=heartbeat, stop=threading.Event(), max_steps=2)
    beat = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert calls["n"] == 2
    assert beat["venue"] == "simulated"
    assert beat["action"] == "hold"  # no promotion in the fixture: never trades


def test_unknown_venue_is_refused(settings: TerminalSettings) -> None:
    with pytest.raises(ValueError):
        build_trader(settings, venue_name="mainnet")


@pytest.mark.skipif(shutil.which("risk-management-engine") is None, reason="CLI not installed")
def test_cli_risk_gate_uses_risk_management_engine(tmp_path: Path) -> None:
    journal = PaperJournal(tmp_path / "paper")
    gate = CliRiskGate(tmp_path / "work", journal)
    small = OrderIntent("qt-1", "BTCUSDT", "buy", Decimal("0.001"),
                        datetime(2026, 11, 17, tzinfo=UTC).isoformat())
    ok, why = gate.approve(small, price=Decimal("65000"), cash=Decimal("10000"),
                           position=Decimal("0"), equity=Decimal("10000"))
    assert ok, why
    big = OrderIntent("qt-2", "BTCUSDT", "buy", Decimal("0.1"), small.submitted_at)
    ok, why = gate.approve(big, price=Decimal("65000"), cash=Decimal("10000"),
                           position=Decimal("0"), equity=Decimal("10000"))
    assert not ok and "notional" in why
