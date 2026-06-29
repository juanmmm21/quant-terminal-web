from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quant_terminal_api.models import (
    AuditEventResponse,
    EquityCurveResponse,
    EquityPointResponse,
    PerformanceMetricsResponse,
    TradeFillResponse,
    TradesResponse,
)

logger = logging.getLogger(__name__)


class DataSourceError(Exception):
    """Raised when ecosystem data cannot be read."""


def _utc_from_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class AuditReader:
    """Reads audit events directly from trade-audit-logger SQLite schema."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def fetch_events(
        self,
        *,
        limit: int = 50,
        event_type: str | None = None,
        symbol: str | None = None,
    ) -> list[AuditEventResponse]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not self._database_path.exists():
            raise DataSourceError(f"audit database not found: {self._database_path}")

        query = """
            SELECT event_id, event_type, symbol, correlation_id,
                   occurred_at, severity, payload_json
            FROM audit_events
            WHERE 1=1
        """
        params: list[Any] = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)

        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self._database_path)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as exc:
            raise DataSourceError(f"failed to query audit database: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()

        events: list[AuditEventResponse] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError as exc:
                logger.warning("skipping corrupt payload for event %s: %s", row["event_id"], exc)
                continue
            events.append(
                AuditEventResponse(
                    event_id=row["event_id"],
                    symbol=row["symbol"],
                    event_type=row["event_type"],
                    correlation_id=row["correlation_id"],
                    occurred_at=_utc_from_iso8601(row["occurred_at"]),
                    severity=row["severity"],
                    payload=payload,
                )
            )
        return events


class MetricsReader:
    """Reads quant-metrics-calculator JSON output."""

    def __init__(self, metrics_path: Path) -> None:
        self._metrics_path = metrics_path

    def load(self) -> PerformanceMetricsResponse:
        if not self._metrics_path.exists():
            raise DataSourceError(f"metrics file not found: {self._metrics_path}")

        try:
            raw = json.loads(self._metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"failed to read metrics file: {exc}") from exc

        if not isinstance(raw, dict):
            raise DataSourceError("metrics file must be a JSON object")

        symbol = str(raw.get("symbol", "UNKNOWN"))
        computed_at_raw = raw.get("computed_at")
        computed_at = (
            _utc_from_iso8601(computed_at_raw) if isinstance(computed_at_raw, str) else None
        )

        return PerformanceMetricsResponse(
            symbol=symbol,
            sharpe_ratio=str(raw.get("sharpe_ratio", "0")),
            sortino_ratio=str(raw.get("sortino_ratio", "0")),
            profit_factor=str(raw.get("profit_factor", "0")),
            max_drawdown_pct=str(raw.get("max_drawdown_pct", "0")),
            total_return_pct=str(raw.get("total_return_pct", "0")),
            win_rate=str(raw.get("win_rate", "0")),
            trade_count=int(raw.get("trade_count", 0)),
            computed_at=computed_at,
        )


class EquityReader:
    """Reads equity curve JSON from quant-metrics-calculator / event-driven-backtester."""

    def __init__(self, equity_path: Path) -> None:
        self._equity_path = equity_path

    def load(self) -> EquityCurveResponse:
        if not self._equity_path.exists():
            raise DataSourceError(f"equity file not found: {self._equity_path}")

        try:
            raw = json.loads(self._equity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"failed to read equity file: {exc}") from exc

        symbol = "UNKNOWN"
        currency = "USDT"
        label = "Capital de la cuenta"
        initial_capital = "0"
        current_capital = "0"
        points_raw: list[dict[str, Any]]
        if isinstance(raw, dict):
            symbol = str(raw.get("symbol", symbol))
            currency = str(raw.get("currency", currency))
            label = str(raw.get("label", label))
            initial_capital = str(raw.get("initial_capital", "0"))
            current_capital = str(raw.get("current_capital", "0"))
            curve = raw.get("equity_curve", raw.get("points", []))
            if not isinstance(curve, list):
                raise DataSourceError("equity_curve must be a list")
            points_raw = curve
        elif isinstance(raw, list):
            points_raw = raw
        else:
            raise DataSourceError("equity file must be a list or object with equity_curve")

        points: list[EquityPointResponse] = []
        for item in points_raw:
            if not isinstance(item, dict):
                continue
            event_time = item.get("event_time")
            equity = item.get("equity")
            if not isinstance(event_time, str) or equity is None:
                continue
            points.append(
                EquityPointResponse(
                    event_time=_utc_from_iso8601(event_time),
                    equity=str(equity),
                )
            )
        points.sort(key=lambda point: point.event_time)
        if initial_capital == "0" and points:
            initial_capital = points[0].equity
        if current_capital == "0" and points:
            current_capital = points[-1].equity
        return EquityCurveResponse(
            symbol=symbol,
            currency=currency,
            label=label,
            initial_capital=initial_capital,
            current_capital=current_capital,
            points=points,
        )


class TradesReader:
    """Reads trade fills JSONL compatible with quant-metrics-calculator."""

    def __init__(self, trades_path: Path) -> None:
        self._trades_path = trades_path

    def load(self) -> TradesResponse:
        if not self._trades_path.exists():
            raise DataSourceError(f"trades file not found: {self._trades_path}")

        try:
            lines = self._trades_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise DataSourceError(f"failed to read trades file: {exc}") from exc

        trades: list[TradeFillResponse] = []
        closed_round_trips = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            filled_at = item.get("filled_at")
            if not isinstance(filled_at, str):
                continue
            pnl_raw = item.get("realized_pnl")
            realized_pnl = str(pnl_raw) if pnl_raw is not None else None
            if realized_pnl is not None:
                closed_round_trips += 1
            trades.append(
                TradeFillResponse(
                    order_id=str(item.get("order_id", "")),
                    symbol=str(item.get("symbol", "")),
                    side=str(item.get("side", "")),
                    quantity=str(item.get("quantity", "0")),
                    price=str(item.get("price", "0")),
                    commission=str(item.get("commission", "0")),
                    filled_at=_utc_from_iso8601(filled_at),
                    realized_pnl=realized_pnl,
                    label=str(item.get("label")) if item.get("label") else None,
                )
            )
        trades.sort(key=lambda trade: trade.filled_at, reverse=True)
        return TradesResponse(
            trades=trades,
            count=len(trades),
            closed_round_trips=closed_round_trips,
        )
