#!/usr/bin/env python3
"""
Orquesta el pipeline completo del ecosistema quant-core-infra.
  ticks → market-data-lakehouse → ta-indicators → alpha-signal-generator
  → risk-management-engine → order-routing-gateway (paper)
  → quant-metrics-calculator → trade-audit-logger → data/ecosystem/

Sin imports cruzados: solo subprocess y archivos JSON/JSONL/SQLite.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ecosystem_tools import (
    annotate_trade_labels,
    build_audit_events,
    build_equity_from_fills,
    ecosystem_dir,
    enrich_metrics,
    export_lakehouse_candles_jsonl,
    filter_approved_orders,
    indicators_json_to_candles_jsonl,
    intermediate_dir,
    project_root,
    resolve_cli,
    resolve_ticks_source,
    routing_results_to_fills,
    run_cli,
    signals_json_to_jsonl,
    signals_to_orders,
    write_jsonl,
)

from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_STRATEGIES = ("rsi_mean_reversion", "macd_crossover")


def run_alpha_signals(
    *,
    enriched_candles: Path,
    symbol: str,
    work: Path,
    strategies: tuple[str, ...] = DEFAULT_STRATEGIES,
) -> tuple[list[dict[str, Any]], str]:
    alpha_cli = resolve_cli("alpha-signal-generator")
    for strategy in strategies:
        signals_json = work / f"signals_{strategy}.json"
        run_cli(
            [
                alpha_cli,
                "run",
                "--candles",
                str(enriched_candles),
                "--symbol",
                symbol,
                "--strategy",
                strategy,
                "--output",
                str(signals_json),
            ]
        )
        payload = json.loads(signals_json.read_text(encoding="utf-8"))
        if isinstance(payload, list) and payload:
            return payload, strategy
    return [], strategies[0]


def ingest_lakehouse(
    ticks_path: Path,
    lake_root: Path,
    *,
    symbol: str,
    timeframe: str,
) -> None:
    cli = resolve_cli("market-data-lakehouse")
    run_cli(
        [
            cli,
            "ingest",
            "--input",
            str(ticks_path),
            "--root",
            str(lake_root),
            "--exchange",
            "binance",
            "--symbol",
            symbol,
            "--timeframes",
            timeframe,
            "--flush-batch-size",
            "200",
        ]
    )


def run_pipeline(
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    strategy: str = "rsi_mean_reversion",
    initial_capital: str = "10000",
    position_size: str = "0.01",
    ticks_path: Path | None = None,
    skip_lakehouse: bool = False,
) -> Path:
    root = project_root()
    lake_root = root / "data" / "lake"
    eco = ecosystem_dir()
    work = intermediate_dir()
    work.mkdir(parents=True, exist_ok=True)
    eco.mkdir(parents=True, exist_ok=True)

    ticks = ticks_path or resolve_ticks_source()
    correlation_id = f"run-{datetime.now(tz=UTC).strftime('%Y-%m-%d')}"
    logger.info("tick source: %s", ticks)

    if not skip_lakehouse:
        ingest_lakehouse(ticks, lake_root, symbol=symbol, timeframe=timeframe)

    candles_jsonl = work / "candles.jsonl"
    candle_count = export_lakehouse_candles_jsonl(
        lake_root,
        candles_jsonl,
        symbol=symbol,
        timeframe=timeframe,
    )
    logger.info("exported %s candles to %s", candle_count, candles_jsonl)

    ta_cli = resolve_cli("ta-indicators-from-scratch")
    indicators_json = work / "indicators.json"
    run_cli(
        [
            ta_cli,
            "compute",
            "--input",
            str(candles_jsonl),
            "--indicator",
            "all",
            "--output",
            str(indicators_json),
        ]
    )

    enriched_candles = work / "candles_with_indicators.jsonl"
    indicators_json_to_candles_jsonl(
        indicators_json,
        enriched_candles,
        event_times_source=candles_jsonl,
    )

    strategy_chain = tuple(dict.fromkeys((strategy, *DEFAULT_STRATEGIES)))
    signals_payload, strategy_used = run_alpha_signals(
        enriched_candles=enriched_candles,
        symbol=symbol,
        work=work,
        strategies=strategy_chain,
    )
    if not isinstance(signals_payload, list):
        raise RuntimeError("alpha-signal-generator output must be a JSON array")
    if not signals_payload:
        logger.warning("no signals generated; writing empty ecosystem outputs")
        _write_empty_outputs(eco, symbol=symbol, initial_capital=initial_capital)
        return eco

    signals_json = work / f"signals_{strategy_used}.json"
    signals_jsonl = work / "signals.jsonl"
    signals_json_to_jsonl(signals_json, signals_jsonl)

    orders = signals_to_orders(signals_payload, symbol=symbol, quantity=position_size)
    orders_jsonl = work / "orders.jsonl"
    write_jsonl(orders_jsonl, orders)

    portfolio_json = work / "portfolio.json"
    portfolio_json.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "cash": initial_capital,
                "equity": initial_capital,
                "position_quantity": "0",
                "average_entry_price": "0",
                "daily_realized_pnl": "0",
                "peak_equity_today": initial_capital,
                "snapshot_time": datetime.now(tz=UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    risk_cli = resolve_cli("risk-management-engine")
    risk_json = work / "risk_results.json"
    risk_proc = run_cli(
        [
            risk_cli,
            "check",
            "--orders",
            str(orders_jsonl),
            "--portfolio",
            str(portfolio_json),
            "--symbol",
            symbol,
            "--no-require-stop-loss",
            "--output",
            str(risk_json),
        ]
    )
    risk_results = json.loads(risk_json.read_text(encoding="utf-8"))
    if not isinstance(risk_results, list):
        raise RuntimeError("risk-management-engine output must be a JSON array")

    approved_orders = filter_approved_orders(orders, risk_results)
    approved_jsonl = work / "approved_orders.jsonl"
    write_jsonl(approved_jsonl, approved_orders)

    gateway_cli = resolve_cli("order-routing-gateway")
    routing_json = work / "routing_results.json"
    if approved_orders:
        run_cli(
            [
                gateway_cli,
                "route",
                "--orders",
                str(approved_jsonl),
                "--ticks",
                str(ticks),
                "--symbol",
                symbol,
                "--exchange",
                "binance",
                "--mode",
                "paper",
                "--commission-rate",
                "0.001",
                "--output",
                str(routing_json),
            ]
        )
        routing_results = json.loads(routing_json.read_text(encoding="utf-8"))
    else:
        logger.warning("no approved orders after risk checks")
        routing_results = []

    fills = routing_results_to_fills(routing_results)
    trades = annotate_trade_labels(fills)
    fills_jsonl = work / "fills.jsonl"
    write_jsonl(fills_jsonl, fills)

    equity_payload = build_equity_from_fills(
        fills,
        symbol=symbol,
        initial_capital=initial_capital,
    )
    equity_for_metrics = work / "equity_for_metrics.json"
    equity_for_metrics.write_text(
        json.dumps(equity_payload["equity_curve"], indent=2) + "\n",
        encoding="utf-8",
    )

    metrics_cli = resolve_cli("quant-metrics-calculator")
    metrics_raw = work / "metrics_raw.json"
    if fills:
        run_cli(
            [
                metrics_cli,
                "compute",
                "--fills",
                str(fills_jsonl),
                "--equity",
                str(equity_for_metrics),
                "--symbol",
                symbol,
                "--output",
                str(metrics_raw),
            ]
        )
        metrics = enrich_metrics(
            json.loads(metrics_raw.read_text(encoding="utf-8")),
            symbol=symbol,
        )
    else:
        metrics = enrich_metrics(
            {
                "sharpe_ratio": "0",
                "sortino_ratio": "0",
                "profit_factor": "0",
                "max_drawdown_pct": "0",
                "total_return_pct": "0",
                "win_rate": "0",
                "trade_count": 0,
            },
            symbol=symbol,
        )

    audit_events = build_audit_events(
        symbol=symbol,
        correlation_id=correlation_id,
        signals=signals_payload,
        risk_results=risk_results,
        routing_results=routing_results if isinstance(routing_results, list) else [],
        metrics=metrics,
    )
    audit_jsonl = work / "audit_events.jsonl"
    write_jsonl(audit_jsonl, audit_events)

    audit_db = eco / "audit.db"
    if audit_db.exists():
        audit_db.unlink()
    audit_cli = resolve_cli("trade-audit-logger")
    run_cli(
        [
            audit_cli,
            "ingest",
            "--input",
            str(audit_jsonl),
            "--db",
            str(audit_db),
        ]
    )

    (eco / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (eco / "equity.json").write_text(json.dumps(equity_payload, indent=2) + "\n", encoding="utf-8")
    write_jsonl(eco / "trades.jsonl", trades)

    manifest = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy_used,
        "tick_source": str(ticks),
        "signal_count": len(signals_payload),
        "fill_count": len(fills),
        "modules": [
            "market-data-lakehouse",
            "ta-indicators-from-scratch",
            "alpha-signal-generator",
            "risk-management-engine",
            "order-routing-gateway",
            "quant-metrics-calculator",
            "trade-audit-logger",
        ],
    }
    (eco / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    logger.info("ecosystem outputs written to %s", eco)
    return eco


def _write_empty_outputs(eco: Path, *, symbol: str, initial_capital: str) -> None:
    metrics = enrich_metrics(
        {
            "sharpe_ratio": "0",
            "sortino_ratio": "0",
            "profit_factor": "0",
            "max_drawdown_pct": "0",
            "total_return_pct": "0",
            "win_rate": "0",
            "trade_count": 0,
        },
        symbol=symbol,
    )
    equity = build_equity_from_fills([], symbol=symbol, initial_capital=initial_capital)
    (eco / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (eco / "equity.json").write_text(json.dumps(equity, indent=2) + "\n", encoding="utf-8")
    write_jsonl(eco / "trades.jsonl", [])
    audit_db = eco / "audit.db"
    if audit_db.exists():
        audit_db.unlink()
    audit_jsonl = eco / "intermediate_audit.jsonl"
    write_jsonl(audit_jsonl, [])
    audit_cli = resolve_cli("trade-audit-logger")
    run_cli([audit_cli, "ingest", "--input", str(audit_jsonl), "--db", str(audit_db)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full quant-core-infra pipeline into data/ecosystem/")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--strategy", default="rsi_mean_reversion")
    parser.add_argument("--initial-capital", default="10000")
    parser.add_argument("--position-size", default="0.01")
    parser.add_argument("--ticks", default=None, help="Ticks JSONL path (default: auto-detect)")
    parser.add_argument("--skip-lakehouse", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ticks = Path(args.ticks).resolve() if args.ticks else None
    try:
        eco = run_pipeline(
            symbol=args.symbol.upper(),
            timeframe=args.timeframe,
            strategy=args.strategy,
            initial_capital=args.initial_capital,
            position_size=args.position_size,
            ticks_path=ticks,
            skip_lakehouse=args.skip_lakehouse,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        logger.exception("pipeline failed")
        raise SystemExit(f"pipeline failed: {exc}") from exc

    print(f"ecosystem ready: {eco}")
    print("set TERMINAL_DATA_MODE=ecosystem or restart API to pick up data/ecosystem/")


if __name__ == "__main__":
    main()
