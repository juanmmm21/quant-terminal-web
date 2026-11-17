"""The paper trader: one deterministic ``step`` per cycle, safe to run 24/7.

Order of checks in every step (any of them can stop new orders; none stops reconciliation):

1. **Emergency stop** — bot state ``panic``: cancel everything at the venue, retrying every step
   while the exchange is unreachable (``kill_pending``); never send a new order.
2. **Reconcile** intents whose outcome is unknown (timeout, disconnect, crash between sending
   and recording): ask the venue by client order id; book a fill exactly once, or drop the
   intent if the exchange never received it. While anything is unknown, nothing new is sent.
3. **Pause**, **no promoted strategy**, **stale market data** — hold.
4. **Target** — the promoted strategy's latest recommendation: ``buy`` → long ``quantity``,
   ``sell`` → flat, anything else → keep.
5. **Risk** — ``RiskGate`` (risk-management-engine) and hard caps; then the intent is written to
   the journal *before* it is sent.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from quant_terminal_api.paper.journal import PaperJournal
from quant_terminal_api.paper.market import MarketView
from quant_terminal_api.paper.venue import (
    ExecutionVenue,
    OrderIntent,
    VenueReport,
    VenueStatus,
    VenueUnavailableError,
)

logger = logging.getLogger(__name__)


class RiskGate(Protocol):
    def approve(self, intent: OrderIntent, *, price: Decimal, cash: Decimal,
                position: Decimal, equity: Decimal) -> tuple[bool, str]: ...


class CliRiskGate:
    """Pre-trade check by ``risk-management-engine check`` (subprocess, JSON files)."""

    def __init__(self, workdir: Path, journal: PaperJournal, cli: str | None = None,
                 extra_args: tuple[str, ...] = ("--no-require-stop-loss",)) -> None:
        import shutil

        self._workdir = workdir
        self._journal = journal
        self._cli = cli or shutil.which("risk-management-engine") or "risk-management-engine"
        self._extra = extra_args

    def approve(self, intent: OrderIntent, *, price: Decimal, cash: Decimal,
                position: Decimal, equity: Decimal) -> tuple[bool, str]:
        import subprocess

        self._workdir.mkdir(parents=True, exist_ok=True)
        orders = self._workdir / "risk_order.jsonl"
        portfolio = self._workdir / "risk_portfolio.json"
        output = self._workdir / "risk_result.json"
        state = self._journal.state
        orders.write_text(json.dumps({
            "client_order_id": intent.client_order_id, "symbol": intent.symbol,
            "side": intent.side, "quantity": str(intent.quantity),
            "reference_price": str(price), "submitted_at": intent.submitted_at,
        }) + "\n", encoding="utf-8")
        portfolio.write_text(json.dumps({
            "symbol": intent.symbol, "cash": str(max(cash, Decimal("0"))),
            "equity": str(equity), "position_quantity": str(position),
            "average_entry_price": state.average_price if position > 0 else "0",
            "daily_realized_pnl": "0",
            "peak_equity_today": str(max(Decimal(state.peak_equity), equity)),
            "snapshot_time": intent.submitted_at,
        }), encoding="utf-8")
        try:
            proc = subprocess.run(
                [self._cli, "--log-level", "WARNING", "check", "--orders", str(orders),
                 "--portfolio", str(portfolio), "--symbol", intent.symbol, *self._extra,
                 "--output", str(output)],
                check=False, capture_output=True, text=True, timeout=30,
            )
            results = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return False, f"risk engine unavailable: {exc}"  # fail closed
        if proc.returncode != 0 or not results:
            return False, f"risk engine failed: {proc.stderr[-200:]}"
        verdict = results[0]
        if verdict.get("verdict") != "approved":
            return False, "; ".join(v.get("message", "") for v in verdict.get("violations", []))
        return True, "approved by risk-management-engine"


class CombinedRiskGate:
    def __init__(self, *gates: RiskGate) -> None:
        self._gates = gates

    def approve(self, intent: OrderIntent, *, price: Decimal, cash: Decimal,
                position: Decimal, equity: Decimal) -> tuple[bool, str]:
        for gate in self._gates:
            ok, why = gate.approve(intent, price=price, cash=cash, position=position,
                                   equity=equity)
            if not ok:
                return False, why
        return True, "ok"


class CapsRiskGate:
    """Hard caps that always apply (the CLI gate below adds risk-management-engine rules)."""

    def __init__(self, max_position: Decimal, max_order_notional: Decimal) -> None:
        self._max_position = max_position
        self._max_order_notional = max_order_notional

    def approve(self, intent: OrderIntent, *, price: Decimal, cash: Decimal,
                position: Decimal, equity: Decimal) -> tuple[bool, str]:
        notional = intent.quantity * price
        if notional > self._max_order_notional:
            return False, f"order notional {notional:.2f} > cap {self._max_order_notional}"
        after = position + (intent.quantity if intent.side == "buy" else -intent.quantity)
        if after > self._max_position:
            return False, f"position {after} would exceed cap {self._max_position}"
        if after < 0:
            return False, "would go short (long-only strategy)"
        if intent.side == "buy" and notional > cash:
            return False, "insufficient paper cash"
        return True, "ok"


@dataclass(frozen=True, slots=True)
class TraderConfig:
    symbol: str = "BTCUSDT"
    quantity: Decimal = Decimal("0.001")
    max_position: Decimal = Decimal("0.01")
    max_order_notional: Decimal = Decimal("1000")


@dataclass(frozen=True, slots=True)
class StepResult:
    action: str
    detail: str = ""


class PaperTrader:
    def __init__(
        self,
        *,
        config: TraderConfig,
        journal: PaperJournal,
        venue: ExecutionVenue,
        market: Callable[[], MarketView],
        bot_status: Callable[[], str],
        promotion: Callable[[], dict[str, Any] | None],
        recommendation: Callable[[str], dict[str, Any] | None],
        risk: RiskGate | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.journal = journal
        self.venue = venue
        self._market = market
        self._bot_status = bot_status
        self._promotion = promotion
        self._recommendation = recommendation
        self._risk = risk or CapsRiskGate(config.max_position, config.max_order_notional)
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    # -- state helpers -------------------------------------------------------------------
    @property
    def position(self) -> Decimal:
        return Decimal(self.journal.state.position)

    @property
    def cash(self) -> Decimal:
        return Decimal(self.journal.state.cash)

    def equity(self, price: Decimal | None) -> Decimal:
        mark = price if price is not None else Decimal(self.journal.state.average_price)
        return self.cash + self.position * mark

    def _halt(self, reason: str) -> StepResult:
        if self.journal.state.halted_reason != reason:
            self.journal.event("halt", reason=reason)
        self.journal.state.halted_reason = reason
        return StepResult("hold", reason)

    # -- the cycle -----------------------------------------------------------------------
    def step(self) -> StepResult:
        now = self._clock()
        state = self.journal.state
        state.last_step_at = now.isoformat()
        try:
            return self._step(now)
        finally:
            self.journal.save()

    def _step(self, now: datetime) -> StepResult:
        state = self.journal.state
        market = self._market()
        if market.price is not None:
            equity = self.equity(market.price)
            day = now.date().isoformat()
            if state.peak_equity_day != day:  # new UTC day: the daily peak restarts
                state.peak_equity_day = day
                state.peak_equity = str(equity)
            elif equity > Decimal(state.peak_equity):
                state.peak_equity = str(equity)
            self.journal.append("equity.jsonl", {
                "at": now.isoformat(), "price": str(market.price),
                "position": state.position, "cash": state.cash,
                "equity": str(self.equity(market.price)), "stale": market.stale,
            })

        status = self._bot_status()
        if status == "panic":
            return self._emergency_stop()
        if state.kill_pending:  # panic was reset while a cancel was still owed
            state.kill_pending = False

        if state.pending and not self._reconcile():
            return self._halt("waiting to reconcile orders with unknown state")

        if status == "paused":
            return self._halt("bot paused")
        promotion = self._promotion()
        if promotion is None:
            return self._halt("no strategy promoted to paper trading")
        if market.stale or market.price is None:
            return self._halt(f"market data not usable: {market.reason}")

        recommendation = self._recommendation(str(promotion.get("timeframe", "1h")))
        if recommendation is None:
            return self._halt("no analysis for the promoted timeframe")
        if recommendation.get("strategy_id") != promotion.get("strategy"):
            state.halted_reason = None
            return StepResult("hold", "latest analysis comes from another strategy")

        verdict = recommendation.get("verdict")
        target = self.config.quantity if verdict == "buy" else (
            Decimal("0") if verdict == "sell" else self.position
        )
        delta = target - self.position
        state.halted_reason = None
        if delta == 0:
            return StepResult("hold", f"at target ({verdict})")
        side = "buy" if delta > 0 else "sell"
        return self._send(side, abs(delta), market.price, now, str(verdict))

    def _send(self, side: str, quantity: Decimal, price: Decimal, now: datetime,
              reason: str) -> StepResult:
        state = self.journal.state
        state.sequence += 1
        intent = OrderIntent(
            client_order_id=f"qt-{state.started_at[:10].replace('-', '')}-{state.sequence}",
            symbol=self.config.symbol,
            side=side,
            quantity=quantity,
            submitted_at=now.isoformat(),
        )
        approved, why = self._risk.approve(intent, price=price, cash=self.cash,
                                           position=self.position, equity=self.equity(price))
        if not approved:
            self.journal.event("risk_rejected", client_order_id=intent.client_order_id,
                               reason=why)
            return StepResult("rejected_by_risk", why)

        # Write-ahead: the intent is durable before it leaves the process.
        state.pending[intent.client_order_id] = {
            "side": side, "quantity": str(quantity), "submitted_at": intent.submitted_at,
            "reason": reason,
        }
        self.journal.save()
        try:
            report = self.venue.submit(intent)
        except VenueUnavailableError as exc:
            self.journal.event("unknown_outcome", client_order_id=intent.client_order_id,
                               error=str(exc))
            return StepResult("unknown", str(exc))
        self._apply(intent.client_order_id, report)
        return StepResult(report.status.value, intent.client_order_id)

    def _reconcile(self) -> bool:
        """True when nothing is left in an unknown state."""
        state = self.journal.state
        for client_id in list(state.pending):
            try:
                report = self.venue.query(self.config.symbol, client_id)
            except VenueUnavailableError as exc:
                self.journal.event("reconcile_failed", client_order_id=client_id, error=str(exc))
                return False
            if report is None:
                # The exchange never saw it: safe to forget; the next step decides afresh.
                state.pending.pop(client_id)
                self.journal.event("reconciled_absent", client_order_id=client_id)
                continue
            self._apply(client_id, report)
            self.journal.event("reconciled", client_order_id=client_id,
                               status=report.status.value)
        return not state.pending

    def _apply(self, client_id: str, report: VenueReport) -> None:
        state = self.journal.state
        intent = state.pending.get(client_id)
        if report.status is VenueStatus.ACCEPTED:
            return  # still working at the exchange: stays pending, reconciled next step
        state.pending.pop(client_id, None)
        if report.status is not VenueStatus.FILLED and report.filled_quantity == 0:
            self.journal.event("order_closed", client_order_id=client_id,
                               status=report.status.value, message=report.message)
            return
        if client_id in state.booked or intent is None or report.average_price is None:
            return
        side = intent["side"]
        qty = report.filled_quantity
        notional = qty * report.average_price
        position = Decimal(state.position)
        cash = Decimal(state.cash)
        if side == "buy":
            new_position = position + qty
            avg = (Decimal(state.average_price) * position + notional) / new_position
            cash -= notional + report.commission
            state.average_price = str(avg)
        else:
            new_position = position - qty
            cash += notional - report.commission
            if new_position == 0:
                state.average_price = "0"
        state.position = str(new_position)
        state.cash = str(cash)
        state.booked.append(client_id)
        self.journal.append("fills.jsonl", {
            "client_order_id": client_id, "side": side, "quantity": str(qty),
            "price": str(report.average_price), "commission": str(report.commission),
            "venue": self.venue.name, "filled_at": self._clock().isoformat(),
            "reason": intent.get("reason"),
        })

    def _emergency_stop(self) -> StepResult:
        state = self.journal.state
        if not state.kill_pending and state.halted_reason == "emergency stop: all orders cancelled":
            return StepResult("killed", "emergency stop already applied")
        state.kill_pending = True
        try:
            cancelled = self.venue.cancel_all(self.config.symbol)
        except VenueUnavailableError as exc:
            self.journal.event("kill_retry", error=str(exc))
            state.halted_reason = "emergency stop: cancel pending (exchange unreachable)"
            return StepResult("kill_pending", str(exc))
        state.kill_pending = False
        state.halted_reason = "emergency stop: all orders cancelled"
        self.journal.event("killed", cancelled=cancelled)
        return StepResult("killed", f"cancelled {cancelled} open orders")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
