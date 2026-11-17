#!/usr/bin/env python3
"""
Compare the paper-trading P&L with what the backtest predicted for the same period.

Paper side: data/paper/{state.json, fills.jsonl, equity.jsonl} written by quant-paper-trader.
Backtest side: event-driven-backtester run on the promoted timeframe's candles from the lakehouse
over the same period, with the same strategy signals (moved to the bar close), position size and
commission. Writes data/paper/comparison.json, served read-only at /api/v1/public/paper.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ecosystem_tools import project_root, resolve_cli, run_cli  # noqa: E402
from strategy_validation import (  # noqa: E402
    TIMEFRAME_SECONDS,
    candles_to_close_ticks,
    parse_time,
    read_jsonl,
    shift_signals_to_bar_close,
    write_jsonl,
)

logger = logging.getLogger(__name__)
MAX_POINTS = 500


def downsample(points: list[dict[str, Any]], limit: int = MAX_POINTS) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return points
    step = len(points) / limit
    picked = [points[int(i * step)] for i in range(limit)]
    if picked[-1] is not points[-1]:
        picked[-1] = points[-1]
    return picked


def paper_side(paper_dir: Path, start: datetime) -> dict[str, Any]:
    state = json.loads((paper_dir / "state.json").read_text(encoding="utf-8"))
    equity_rows = [r for r in read_jsonl(paper_dir / "equity.jsonl")
                   if parse_time(r["at"]) >= start] if (paper_dir / "equity.jsonl").exists() else []
    fills = [f for f in read_jsonl(paper_dir / "fills.jsonl")
             if parse_time(f["filled_at"]) >= start] if (paper_dir / "fills.jsonl").exists() else []
    initial = Decimal(state["initial_cash"])
    last_equity = Decimal(equity_rows[-1]["equity"]) if equity_rows else initial
    return {
        "initial_equity": str(initial),
        "final_equity": str(last_equity),
        "pnl": str(last_equity - initial),
        "return_pct": float((last_equity - initial) / initial),
        "fills": len(fills),
        "commission_paid": str(sum((Decimal(f["commission"]) for f in fills), Decimal("0"))),
        "equity_curve": downsample([{"at": r["at"], "equity": r["equity"]} for r in equity_rows]),
    }


def backtest_side(
    *, symbol: str, timeframe: str, strategy: str, start: datetime, end: datetime,
    quantity: str, initial_cash: str, work: Path,
) -> dict[str, Any]:
    lake_tf = "1m" if timeframe in ("10m", "15m") else timeframe
    bar = TIMEFRAME_SECONDS[lake_tf]
    candles_path = work / f"candles_{timeframe}.jsonl"
    signals_src = work / f"signals_{strategy}_{timeframe}.json"
    if not candles_path.exists() or not signals_src.exists():
        raise FileNotFoundError("analysis work files missing; the market daemon writes them")
    candles = [c for c in read_jsonl(candles_path)
               if start - timedelta(seconds=bar) <= parse_time(str(c["event_time"])) < end]
    if not candles:
        raise ValueError("no candles in the paper period yet")
    ticks = candles_to_close_ticks(candles, symbol=symbol, bar_seconds=bar)
    signals = [s for s in shift_signals_to_bar_close(
        json.loads(signals_src.read_text(encoding="utf-8")), bar_seconds=bar)
        if start <= parse_time(str(s["event_time"])) < end]
    out_dir = work / "comparison"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "ticks.jsonl", ticks)
    write_jsonl(out_dir / "signals.jsonl", signals)
    result_path = out_dir / "backtest.json"
    run_cli([resolve_cli("event-driven-backtester"), "run", "--ticks",
             str(out_dir / "ticks.jsonl"), "--signals", str(out_dir / "signals.jsonl"),
             "--symbol", symbol, "--initial-cash", initial_cash, "--position-size", quantity,
             "--commission-rate", "0.001", "--output", str(result_path)])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    final = Decimal(result["final_equity"])
    initial = Decimal(initial_cash)
    return {
        "initial_equity": initial_cash,
        "final_equity": str(final),
        "pnl": str(final - initial),
        "return_pct": float((final - initial) / initial),
        "fills": result["fill_count"],
        "signals_in_period": len(signals),
        "bars": len(candles),
        "equity_curve": downsample([{"at": p["event_time"], "equity": p["equity"]}
                                    for p in result["equity_curve"]]),
    }


def build_comparison(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    end = now or datetime.now(tz=UTC)
    paper_dir = root / "data" / "paper"
    runtime = root / "data" / "runtime"
    promotion = json.loads((runtime / "paper_promotion.json").read_text(encoding="utf-8"))
    state = json.loads((paper_dir / "state.json").read_text(encoding="utf-8"))
    start = max(parse_time(promotion["promoted_at"]), parse_time(state["started_at"]))
    heartbeat_path = paper_dir / "heartbeat.json"
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8")) \
        if heartbeat_path.exists() else {}
    report: dict[str, Any] = {
        "generated_at": end.isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "symbol": promotion.get("symbol", "BTCUSDT"),
        "strategy": promotion["strategy"],
        "timeframe": promotion["timeframe"],
        "venue": heartbeat.get("venue", "binance-testnet"),
        "gate_passed": promotion.get("gate_passed"),
        "validation": promotion.get("validation", {}),
        "disclaimer": (
            "Paper trading on the Binance spot testnet (test funds, testnet order book). "
            "Not real-money performance. The backtest column is a simulation on Binance "
            "mainnet candles for the same period; testnet prices and liquidity differ."
        ),
        "status": {k: heartbeat.get(k) for k in ("at", "action", "halted_reason",
                                                  "kill_pending")},
        "paper": paper_side(paper_dir, start),
    }
    try:
        report["backtest"] = backtest_side(
            symbol=report["symbol"], timeframe=promotion["timeframe"],
            strategy=promotion["strategy"], start=start, end=end,
            quantity=os.environ.get("TERMINAL_PAPER_QUANTITY", "0.001"),
            initial_cash=state["initial_cash"], work=runtime / "work",
        )
        report["tracking_error_pnl"] = str(
            Decimal(report["paper"]["pnl"]) - Decimal(report["backtest"]["pnl"])
        )
    except (FileNotFoundError, ValueError) as exc:
        report["backtest"] = None
        report["backtest_error"] = str(exc)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper P&L vs backtest prediction")
    parser.add_argument("--root", default=str(project_root()))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = Path(args.root)
    report = build_comparison(root)
    output = root / "data" / "paper" / "comparison.json"
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    print(output)


if __name__ == "__main__":
    main()
