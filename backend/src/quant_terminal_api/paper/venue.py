"""Execution venues.

``GatewayCliVenue`` drives ``order-routing-gateway`` (testnet mode) through its CLI: the
integration contract of the ecosystem is the command line and JSON, never imports.
``SimulatedVenue`` is an in-memory exchange with injectable failures for the chaos tests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class VenueStatus(StrEnum):
    FILLED = "filled"
    ACCEPTED = "accepted"  # resting / partially filled
    REJECTED = "rejected"
    CANCELED = "canceled"


class VenueUnavailableError(ConnectionError):
    """No definite answer from the exchange: the order state is unknown."""


@dataclass(frozen=True, slots=True)
class OrderIntent:
    client_order_id: str
    symbol: str
    side: str  # "buy" | "sell"
    quantity: Decimal
    submitted_at: str


@dataclass(frozen=True, slots=True)
class VenueReport:
    client_order_id: str
    status: VenueStatus
    filled_quantity: Decimal = Decimal("0")
    average_price: Decimal | None = None
    commission: Decimal = Decimal("0")
    message: str = ""


class ExecutionVenue(Protocol):
    name: str

    def submit(self, intent: OrderIntent) -> VenueReport: ...

    def query(self, symbol: str, client_order_id: str) -> VenueReport | None: ...

    def cancel_all(self, symbol: str) -> int: ...


_STATUS = {
    "FILLED": VenueStatus.FILLED,
    "NEW": VenueStatus.ACCEPTED,
    "PARTIALLY_FILLED": VenueStatus.ACCEPTED,
    "CANCELED": VenueStatus.CANCELED,
    "EXPIRED": VenueStatus.CANCELED,
    "REJECTED": VenueStatus.REJECTED,
}


class GatewayCliVenue:
    name = "binance-testnet"

    def __init__(self, cli: str | None = None, timeout_seconds: float = 20.0,
                 commission_rate: str = "0.001") -> None:
        self._cli = cli or shutil.which("order-routing-gateway") or "order-routing-gateway"
        self._timeout = timeout_seconds
        self._commission_rate = commission_rate

    def _run(self, *args: str) -> object:
        try:
            proc = subprocess.run(
                [self._cli, "--log-level", "WARNING", *args],
                check=False, capture_output=True, text=True, timeout=self._timeout,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise VenueUnavailableError(str(exc)) from exc
        if proc.returncode == 75:
            raise VenueUnavailableError(proc.stdout.strip() or "exchange unavailable")
        try:
            payload: object = json.loads(proc.stdout or "null")
        except json.JSONDecodeError as exc:
            detail = proc.stderr[-300:]
            raise VenueUnavailableError(f"unparseable gateway output: {detail}") from exc
        if proc.returncode not in (0, 2):
            raise VenueUnavailableError(proc.stderr[-300:] or "gateway failed")
        return payload

    def submit(self, intent: OrderIntent) -> VenueReport:
        order = {
            "client_order_id": intent.client_order_id,
            "symbol": intent.symbol,
            "side": intent.side,
            "order_type": "market",
            "quantity": str(intent.quantity),
            "submitted_at": intent.submitted_at,
        }
        payload = self._run("submit", "--symbol", intent.symbol, "--order-json",
                            json.dumps(order), "--commission-rate", self._commission_rate)
        if not isinstance(payload, dict):
            raise VenueUnavailableError("unexpected submit output")
        if payload.get("error") == "rejected":
            return VenueReport(intent.client_order_id, VenueStatus.REJECTED,
                               message=str(payload.get("detail", "")))
        ack = payload.get("acknowledgement") or {}
        fill = payload.get("fill") or None
        status = VenueStatus(str(ack.get("status", "rejected")))
        if isinstance(fill, dict):
            return VenueReport(
                intent.client_order_id,
                VenueStatus.FILLED,
                filled_quantity=Decimal(str(fill["quantity"])),
                average_price=Decimal(str(fill["fill_price"])),
                commission=Decimal(str(fill["commission"])),
            )
        return VenueReport(intent.client_order_id, status,
                           message=str(ack.get("message", "")))

    def query(self, symbol: str, client_order_id: str) -> VenueReport | None:
        payload = self._run("query", "--symbol", symbol, "--client-order-id", client_order_id)
        if payload is None:
            return None
        if not isinstance(payload, dict) or payload.get("error"):
            raise VenueUnavailableError(f"query failed: {payload}")
        executed = Decimal(str(payload.get("executedQty", "0")))
        quote = Decimal(str(payload.get("cummulativeQuoteQty", "0")))
        average = quote / executed if executed > 0 else None
        return VenueReport(
            client_order_id,
            _STATUS.get(str(payload.get("status")), VenueStatus.REJECTED),
            filled_quantity=executed,
            average_price=average,
            commission=quote * Decimal(self._commission_rate),
        )

    def cancel_all(self, symbol: str) -> int:
        payload = self._run("cancel-all", "--symbol", symbol)
        if isinstance(payload, dict) and payload.get("error"):
            raise VenueUnavailableError(f"cancel-all failed: {payload}")
        return len(payload) if isinstance(payload, list) else 0


@dataclass(slots=True)
class SimulatedVenue:
    """In-memory exchange. Failure switches reproduce the chaos scenarios."""

    price: Decimal = Decimal("65000")
    commission_rate: Decimal = Decimal("0.001")
    name: str = "simulated"
    connected: bool = True
    lose_next_response: bool = False  # accepts the order, then the reply is lost
    rest_orders: bool = False  # accept without filling (resting limit-like orders)
    orders: dict[str, VenueReport] = field(default_factory=dict)
    submissions: list[str] = field(default_factory=list)
    cancel_calls: int = 0

    def _require_connection(self) -> None:
        if not self.connected:
            raise VenueUnavailableError("exchange disconnected")

    def submit(self, intent: OrderIntent) -> VenueReport:
        self._require_connection()
        if intent.client_order_id in self.orders:
            return VenueReport(intent.client_order_id, VenueStatus.REJECTED,
                               message="-2010: duplicate client order id")
        self.submissions.append(intent.client_order_id)
        if self.rest_orders:
            report = VenueReport(intent.client_order_id, VenueStatus.ACCEPTED)
        else:
            report = VenueReport(
                intent.client_order_id, VenueStatus.FILLED, intent.quantity, self.price,
                self.price * intent.quantity * self.commission_rate,
            )
        self.orders[intent.client_order_id] = report
        if self.lose_next_response:
            self.lose_next_response = False
            raise VenueUnavailableError("read timed out after the order was accepted")
        return report

    def query(self, symbol: str, client_order_id: str) -> VenueReport | None:
        self._require_connection()
        return self.orders.get(client_order_id)

    def cancel_all(self, symbol: str) -> int:
        self.cancel_calls += 1
        self._require_connection()
        open_ids = [k for k, v in self.orders.items() if v.status is VenueStatus.ACCEPTED]
        for key in open_ids:
            self.orders[key] = VenueReport(key, VenueStatus.CANCELED)
        return len(open_ids)

    def open_orders(self) -> list[str]:
        return [k for k, v in self.orders.items() if v.status is VenueStatus.ACCEPTED]
