#!/usr/bin/env python3
"""
Utilidades para orquestar el ecosistema quant-core-infra vía CLI y archivos.

Sin imports cruzados entre repos: solo subprocess + transformaciones JSON/JSONL.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def monorepo_root() -> Path:
    return project_root().parent


def ecosystem_dir() -> Path:
    return project_root() / "data" / "ecosystem"


def intermediate_dir() -> Path:
    return ecosystem_dir() / "intermediate"


def resolve_cli(command: str) -> str:
    found = shutil.which(command)
    if found:
        return found
    sibling_venv = monorepo_root() / command / ".venv" / "bin" / command
    if sibling_venv.exists():
        return str(sibling_venv)
    raise FileNotFoundError(
        f"{command} no está en PATH ni en {sibling_venv}. "
        f"Instálalo desde ../{command}"
    )


def run_cli(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    logger.info("running: %s", " ".join(command))
    proc = subprocess.run(command, check=False, text=True, capture_output=True)
    if check and proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip()
        raise subprocess.CalledProcessError(
            proc.returncode,
            command,
            output=proc.stdout,
            stderr=stderr,
        )
    return proc


def count_lakehouse_candles(lake_root: Path, *, symbol: str, timeframe: str) -> int:
    """Cuenta velas disponibles en el lakehouse para un símbolo/timeframe."""
    if not lake_root.exists():
        return 0
    parquet_files = [str(path) for path in lake_root.rglob("candles.parquet")]
    if not parquet_files:
        return 0

    import duckdb

    paths_sql = ", ".join("'" + path.replace("'", "''") + "'" for path in parquet_files)
    connection = duckdb.connect()
    try:
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM read_parquet([{paths_sql}], union_by_name=true)
            WHERE symbol = ? AND timeframe = ?
            """,
            [symbol, timeframe],
        ).fetchone()
    finally:
        connection.close()
    return int(row[0]) if row else 0


def resolve_ticks_source() -> Path:
    candidates = [
        project_root() / "data" / "live" / "ticks.jsonl",
        project_root() / "data" / "bootstrap_ticks.jsonl",
        monorepo_root() / "event-driven-backtester" / "samples" / "btcusdt_ticks.jsonl",
        monorepo_root() / "order-routing-gateway" / "samples" / "btcusdt_ticks.jsonl",
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size > 0:
            return path
    raise FileNotFoundError(
        "no tick source found. Run bootstrap_market_data.py or tick_bridge.py first."
    )


def export_lakehouse_candles_jsonl(
    lake_root: Path,
    output: Path,
    *,
    symbol: str,
    timeframe: str,
    limit: int = 500,
) -> int:
    cli = resolve_cli("market-data-lakehouse")
    proc = run_cli(
        [
            cli,
            "query",
            "--root",
            str(lake_root),
            "--symbol",
            symbol,
            "--timeframe",
            timeframe,
            "--limit",
            str(limit),
        ]
    )
    rows = json.loads(proc.stdout)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"no candles for {symbol} {timeframe}")

    def _row_open_time(row: dict[str, object]) -> str:
        open_time = row.get("open_time", row.get("close_time"))
        if open_time is None:
            return ""
        return str(open_time).replace("Z", "+00:00")

    rows.sort(key=_row_open_time)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            if not isinstance(row, dict):
                continue
            open_time = row.get("open_time", row.get("close_time"))
            if open_time is None:
                continue
            if isinstance(open_time, str):
                event_time = open_time.replace("Z", "+00:00")
            else:
                event_time = str(open_time)
            record = {
                "symbol": symbol,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "event_time": event_time,
            }
            handle.write(json.dumps(record) + "\n")
    return len(rows)


def indicators_json_to_candles_jsonl(
    indicators_path: Path,
    output: Path,
    *,
    event_times_source: Path | None = None,
) -> int:
    payload = json.loads(indicators_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("indicators output must be a JSON object")

    ohlcv = payload.get("ohlcv")
    indicators = payload.get("indicators", {})
    if not isinstance(ohlcv, dict):
        raise ValueError("indicators output missing ohlcv")

    opens = ohlcv.get("open", [])
    highs = ohlcv.get("high", [])
    lows = ohlcv.get("low", [])
    closes = ohlcv.get("close", [])
    volumes = ohlcv.get("volume", [])
    length = len(closes)

    event_times: list[str] = []
    if event_times_source and event_times_source.exists():
        with event_times_source.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if isinstance(record, dict) and "event_time" in record:
                    event_times.append(str(record["event_time"]))

    rsi_values = indicators.get("rsi", {}).get("values", [])
    macd = indicators.get("macd", {})
    macd_line = macd.get("macd_line", []) if isinstance(macd, dict) else []
    signal_line = macd.get("signal_line", []) if isinstance(macd, dict) else []

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for index in range(length):
            record: dict[str, Any] = {
                "open": opens[index] if index < len(opens) else closes[index],
                "high": highs[index] if index < len(highs) else closes[index],
                "low": lows[index] if index < len(lows) else closes[index],
                "close": closes[index],
                "volume": volumes[index] if index < len(volumes) else 0.0,
                "event_time": (
                    event_times[index]
                    if index < len(event_times)
                    else datetime.now(tz=UTC).isoformat()
                ),
            }
            if index < len(rsi_values) and rsi_values[index] is not None:
                record["rsi"] = rsi_values[index]
            if index < len(macd_line) and macd_line[index] is not None:
                record["macd_line"] = macd_line[index]
            if index < len(signal_line) and signal_line[index] is not None:
                record["signal_line"] = signal_line[index]
            handle.write(json.dumps(record) + "\n")
    return length


def signals_json_to_jsonl(signals_path: Path, output: Path) -> int:
    payload = json.loads(signals_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("signals output must be a JSON array")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for item in payload:
            handle.write(json.dumps(item) + "\n")
    return len(payload)


def signals_to_orders(
    signals: list[dict[str, Any]],
    *,
    symbol: str,
    quantity: str,
) -> list[dict[str, str]]:
    orders: list[dict[str, str]] = []
    for index, signal in enumerate(signals, start=1):
        action = str(signal.get("action", ""))
        side = str(signal.get("side", ""))
        event_time = str(signal.get("event_time", datetime.now(tz=UTC).isoformat()))
        reference_price = str(signal.get("reference_price", "0"))
        order_id = f"ord-{index:03d}"
        if action == "enter" and side == "long":
            orders.append(
                {
                    "client_order_id": order_id,
                    "symbol": str(signal.get("symbol", symbol)),
                    "side": "buy",
                    "order_type": "market",
                    "quantity": quantity,
                    "reference_price": reference_price,
                    "submitted_at": event_time,
                }
            )
        elif action == "exit" and side == "long":
            orders.append(
                {
                    "client_order_id": order_id,
                    "symbol": str(signal.get("symbol", symbol)),
                    "side": "sell",
                    "order_type": "market",
                    "quantity": quantity,
                    "reference_price": reference_price,
                    "submitted_at": event_time,
                }
            )
    return orders


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def filter_approved_orders(
    orders: list[dict[str, str]],
    risk_results: list[dict[str, Any]],
) -> list[dict[str, str]]:
    approved_ids = {
        str(item["client_order_id"])
        for item in risk_results
        if str(item.get("verdict", "")) == "approved"
    }
    return [order for order in orders if order["client_order_id"] in approved_ids]


def routing_results_to_fills(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    fills: list[dict[str, str]] = []
    for result in results:
        fill = result.get("fill")
        if not isinstance(fill, dict):
            continue
        fills.append(
            {
                "order_id": str(fill.get("client_order_id", "")),
                "symbol": str(fill.get("symbol", "")),
                "side": str(fill.get("side", "")),
                "quantity": str(fill.get("quantity", "0")),
                "price": str(fill.get("fill_price", "0")),
                "commission": str(fill.get("commission", "0")),
                "filled_at": str(fill.get("filled_at", "")),
            }
        )
    fills.sort(key=lambda item: item["filled_at"])
    return fills


def annotate_trade_labels(fills: list[dict[str, str]]) -> list[dict[str, str]]:
    annotated: list[dict[str, str]] = []
    open_buy: dict[str, str] | None = None
    round_trip = 0
    for fill in fills:
        row = dict(fill)
        side = row.get("side", "")
        if side == "buy":
            row["label"] = "Apertura larga"
            open_buy = row
        elif side == "sell" and open_buy is not None:
            round_trip += 1
            try:
                buy_price = Decimal(open_buy["price"])
                sell_price = Decimal(row["price"])
                qty = Decimal(row["quantity"])
                buy_comm = Decimal(open_buy.get("commission", "0"))
                sell_comm = Decimal(row.get("commission", "0"))
                pnl = (sell_price - buy_price) * qty - buy_comm - sell_comm
                row["realized_pnl"] = str(pnl)
            except Exception:
                row["realized_pnl"] = "0"
            row["label"] = f"Cierre operación #{round_trip}"
            open_buy = None
        else:
            row["label"] = "Operación"
        annotated.append(row)
    return annotated


def build_equity_from_fills(
    fills: list[dict[str, str]],
    *,
    symbol: str,
    initial_capital: str,
) -> dict[str, Any]:
    capital = Decimal(initial_capital)
    points: list[dict[str, str]] = [
        {
            "event_time": datetime.now(tz=UTC).isoformat(),
            "equity": str(capital),
        }
    ]
    if fills:
        points[0]["event_time"] = fills[0]["filled_at"]
        points[0]["equity"] = initial_capital

    position_qty = Decimal("0")
    cash = capital
    for fill in fills:
        qty = Decimal(fill["quantity"])
        price = Decimal(fill["price"])
        commission = Decimal(fill.get("commission", "0"))
        if fill["side"] == "buy":
            cash -= qty * price + commission
            position_qty += qty
        else:
            cash += qty * price - commission
            position_qty -= qty
        mark = price
        equity = cash + position_qty * mark
        points.append(
            {
                "event_time": fill["filled_at"],
                "equity": str(equity),
            }
        )

    current = points[-1]["equity"] if points else initial_capital
    return {
        "symbol": symbol,
        "currency": "USDT",
        "label": "Capital de la cuenta (paper trading)",
        "initial_capital": initial_capital,
        "current_capital": current,
        "equity_curve": points,
    }


def enrich_metrics(metrics: dict[str, Any], *, symbol: str) -> dict[str, Any]:
    enriched = dict(metrics)
    enriched["symbol"] = symbol
    enriched["computed_at"] = datetime.now(tz=UTC).isoformat()
    return enriched


def build_audit_events(
    *,
    symbol: str,
    correlation_id: str,
    signals: list[dict[str, Any]],
    risk_results: list[dict[str, Any]],
    routing_results: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    event_index = 1

    def next_id() -> str:
        nonlocal event_index
        value = f"eco-{event_index:04d}"
        event_index += 1
        return value

    for signal in signals:
        events.append(
            {
                "event_id": next_id(),
                "event_type": "signal_decision",
                "symbol": symbol,
                "correlation_id": correlation_id,
                "occurred_at": str(signal.get("event_time", datetime.now(tz=UTC).isoformat())),
                "severity": "info",
                "payload": {
                    "strategy_id": signal.get("strategy_id"),
                    "action": signal.get("action"),
                    "confidence": signal.get("confidence"),
                    "reason": signal.get("reason"),
                },
            }
        )

    for risk in risk_results:
        events.append(
            {
                "event_id": next_id(),
                "event_type": "risk_check",
                "symbol": symbol,
                "correlation_id": str(risk.get("client_order_id", correlation_id)),
                "occurred_at": str(risk.get("evaluated_at", datetime.now(tz=UTC).isoformat())),
                "severity": "info" if risk.get("verdict") == "approved" else "warning",
                "payload": {
                    "client_order_id": risk.get("client_order_id"),
                    "verdict": risk.get("verdict"),
                    "violations": risk.get("violations", []),
                },
            }
        )

    for result in routing_results:
        ack = result.get("acknowledgement", {})
        if isinstance(ack, dict):
            events.append(
                {
                    "event_id": next_id(),
                    "event_type": "order_submitted",
                    "symbol": symbol,
                    "correlation_id": str(ack.get("client_order_id", correlation_id)),
                    "occurred_at": str(ack.get("submitted_at", datetime.now(tz=UTC).isoformat())),
                    "severity": "info",
                    "payload": {
                        "client_order_id": ack.get("client_order_id"),
                        "status": ack.get("status"),
                        "exchange": ack.get("exchange"),
                    },
                }
            )
        fill = result.get("fill")
        if isinstance(fill, dict):
            payload: dict[str, Any] = {
                "fill_price": fill.get("fill_price"),
                "quantity": fill.get("quantity"),
                "commission": fill.get("commission"),
                "side": fill.get("side"),
            }
            if fill.get("side") == "sell":
                payload["routing_mode"] = "paper"
            events.append(
                {
                    "event_id": next_id(),
                    "event_type": "order_filled",
                    "symbol": symbol,
                    "correlation_id": str(fill.get("client_order_id", correlation_id)),
                    "occurred_at": str(fill.get("filled_at", datetime.now(tz=UTC).isoformat())),
                    "severity": "info",
                    "payload": payload,
                }
            )

    events.append(
        {
            "event_id": next_id(),
            "event_type": "metrics_computed",
            "symbol": symbol,
            "correlation_id": correlation_id,
            "occurred_at": datetime.now(tz=UTC).isoformat(),
            "severity": "info",
            "payload": {
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "profit_factor": metrics.get("profit_factor"),
                "trade_count": metrics.get("trade_count"),
                "source": "quant-metrics-calculator",
            },
        }
    )
    return events


def ecosystem_outputs_ready(eco_dir: Path | None = None) -> bool:
    root = eco_dir or ecosystem_dir()
    required = (
        root / "metrics.json",
        root / "equity.json",
        root / "trades.jsonl",
        root / "audit.db",
    )
    return all(path.exists() and path.stat().st_size > 0 for path in required)
