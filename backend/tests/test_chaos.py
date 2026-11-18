"""Chaos tests for the paper trader: the exchange and the data feed misbehave on purpose."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient

from quant_terminal_api.app import create_app
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.paper.engine import PaperTrader, TraderConfig, read_json
from quant_terminal_api.paper.journal import PaperJournal
from quant_terminal_api.paper.market import MarketView, read_market
from quant_terminal_api.paper.venue import SimulatedVenue, VenueStatus

FRESH = MarketView(Decimal("65000"), False, "fresh")
STALE = MarketView(Decimal("65000"), True, "feed reports stale data")


@dataclass
class World:
    """Everything the trader reads, under the test's control."""

    directory: Path
    venue: SimulatedVenue = field(default_factory=SimulatedVenue)
    market: MarketView = FRESH
    status: str = "running"
    promoted: bool = True
    verdict: str = "buy"
    strategy: str = "rsi_mean_reversion"

    def trader(self) -> PaperTrader:
        return PaperTrader(
            config=TraderConfig(quantity=Decimal("0.001")),
            journal=PaperJournal(self.directory),
            venue=self.venue,
            market=lambda: self.market,
            bot_status=lambda: self.status,
            promotion=lambda: (
                {"strategy": "rsi_mean_reversion", "timeframe": "1h"} if self.promoted else None
            ),
            recommendation=lambda _tf: {"verdict": self.verdict, "strategy_id": self.strategy},
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(directory=tmp_path / "paper")


def _fills(world: World) -> list[dict[str, Any]]:
    return PaperJournal(world.directory).read("fills.jsonl")


def test_happy_path_buys_once_then_holds_then_exits(world: World) -> None:
    trader = world.trader()
    assert trader.step().action == "filled"
    assert trader.step().action == "hold"
    world.verdict = "sell"
    assert trader.step().action == "filled"
    assert trader.position == 0
    assert [f["side"] for f in _fills(world)] == ["buy", "sell"]
    assert trader.cash < Decimal("10000")  # two commissions paid


def test_exchange_disconnected_at_submit_never_double_sends(world: World) -> None:
    trader = world.trader()
    world.venue.connected = False
    assert trader.step().action == "unknown"
    assert trader.step().detail.startswith("waiting to reconcile")
    assert world.venue.submissions == []  # nothing reached the exchange
    world.venue.connected = True
    first = trader.step()  # reconcile: absent -> forget; then decide afresh and send once
    assert first.action == "filled"
    assert len(world.venue.submissions) == 1
    assert trader.position == Decimal("0.001")
    events = [e["kind"] for e in PaperJournal(world.directory).read("events.jsonl")]
    assert "reconciled_absent" in events


def test_reply_lost_mid_order_is_reconciled_and_booked_exactly_once(world: World) -> None:
    trader = world.trader()
    world.venue.lose_next_response = True  # accepted and filled, but the answer never arrives
    assert trader.step().action == "unknown"
    assert trader.position == 0
    assert trader.step().action == "hold"  # reconciled: filled, now at target
    assert world.venue.submissions == [next(iter(world.venue.orders))]
    assert trader.position == Decimal("0.001")
    assert len(_fills(world)) == 1


def test_process_crash_mid_order_is_recovered_by_a_new_process(world: World) -> None:
    world.venue.lose_next_response = True
    world.trader().step()  # the process "dies" here with an unknown order in the journal
    restarted = world.trader()  # new process, same disk
    assert restarted.journal.state.pending
    restarted.step()
    assert restarted.position == Decimal("0.001")
    assert len(world.venue.submissions) == 1 and len(_fills(world)) == 1


def test_order_still_working_blocks_new_orders(world: World) -> None:
    world.venue.rest_orders = True
    trader = world.trader()
    assert trader.step().action == VenueStatus.ACCEPTED.value
    for _ in range(3):
        assert trader.step().detail.startswith("waiting to reconcile")
    assert len(world.venue.submissions) == 1


def test_stale_data_halts_trading_until_fresh(world: World) -> None:
    trader = world.trader()
    world.market = STALE
    result = trader.step()
    assert result.action == "hold" and "stale" in result.detail
    assert world.venue.submissions == []
    world.market = FRESH
    assert trader.step().action == "filled"


def test_emergency_stop_with_exchange_down_retries_and_never_trades(world: World) -> None:
    world.venue.rest_orders = True
    trader = world.trader()
    trader.step()  # one order resting at the exchange
    world.venue.connected = False
    world.status = "panic"
    for _ in range(3):
        result = trader.step()
        assert result.action == "kill_pending"
        assert trader.journal.state.kill_pending
    assert world.venue.cancel_calls == 3  # retried every step
    assert len(world.venue.submissions) == 1  # and nothing new was sent
    world.venue.connected = True
    assert trader.step().action == "killed"
    assert world.venue.open_orders() == []
    assert trader.step().detail == "emergency stop already applied"
    assert len(world.venue.submissions) == 1


def test_panic_endpoint_works_with_the_exchange_disconnected(
    settings: TerminalSettings, tmp_path: Path
) -> None:
    venue = SimulatedVenue(connected=False)
    client = TestClient(create_app(settings))
    response = client.post("/api/v1/bot/panic", json={"reason": "chaos drill"}, headers=ADMIN)
    assert response.status_code == 200  # the API never talks to the exchange to stop
    status = (read_json(settings.bot_state_path) or {}).get("status")
    trader = PaperTrader(
        config=TraderConfig(),
        journal=PaperJournal(tmp_path / "paper"),
        venue=venue,
        market=lambda: FRESH,
        bot_status=lambda: str(status),
        promotion=lambda: {"strategy": "rsi_mean_reversion", "timeframe": "1h"},
        recommendation=lambda _tf: {"verdict": "buy", "strategy_id": "rsi_mean_reversion"},
    )
    assert trader.step().action == "kill_pending"
    assert venue.submissions == []
    unauthenticated = client.post("/api/v1/bot/reset")
    assert unauthenticated.status_code == 401  # and nobody can lift it without a token


def test_risk_caps_and_strategy_mismatch_hold(world: World) -> None:
    trader = PaperTrader(
        config=TraderConfig(quantity=Decimal("0.02"), max_position=Decimal("0.01")),
        journal=PaperJournal(world.directory),
        venue=world.venue,
        market=lambda: FRESH,
        bot_status=lambda: "running",
        promotion=lambda: {"strategy": "rsi_mean_reversion", "timeframe": "1h"},
        recommendation=lambda _tf: {"verdict": "buy", "strategy_id": "rsi_mean_reversion"},
    )
    assert trader.step().action == "rejected_by_risk"
    world.strategy = "macd_crossover"
    other = world.trader()
    assert "another strategy" in other.step().detail
    assert world.venue.submissions == []


def test_no_promotion_or_pause_means_no_orders(world: World) -> None:
    world.promoted = False
    assert "no strategy promoted" in world.trader().step().detail
    world.promoted = True
    world.status = "paused"
    assert world.trader().step().detail == "bot paused"
    assert world.venue.submissions == []


def _status(path: Path, *, stale: bool, at: datetime) -> None:
    path.write_text(json.dumps({"stale": stale, "checked_at": at.isoformat()}), encoding="utf-8")


def test_market_reader_detects_every_kind_of_staleness(tmp_path: Path) -> None:
    now = datetime(2026, 11, 17, 23, 0, tzinfo=UTC)
    ticks = tmp_path / "ticks.jsonl"
    status = tmp_path / "status.json"
    ticks.write_text(json.dumps({"price": "65000", "event_time": now.isoformat()}) + "\n",
                     encoding="utf-8")
    assert read_market(ticks, status, now=now).reason == "feed status file missing"
    _status(status, stale=False, at=now - timedelta(seconds=60))
    assert "not updated" in read_market(ticks, status, now=now).reason
    _status(status, stale=True, at=now)
    assert read_market(ticks, status, now=now).reason == "feed reports stale data"
    _status(status, stale=False, at=now)
    view = read_market(ticks, status, now=now)
    assert not view.stale and view.price == Decimal("65000")
    later = now + timedelta(minutes=5)
    _status(status, stale=False, at=later)
    assert read_market(ticks, status, now=later).reason == "last tick too old"
