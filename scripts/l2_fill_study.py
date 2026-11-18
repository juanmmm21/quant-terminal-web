#!/usr/bin/env python3
"""
Compare simulated limit-order fills with and without the queue-position model on real L2 data.

Pipeline (subprocess only, no cross-repo imports):
  recording (websocket-feed-handler --channels trade depth + REST snapshots)
  → market-data-lakehouse ingest-depth / export-depth
  → order-book-reconstructor replay        (sequence check, resync, verification)
  → limit orders: a systematic probe (best bid / best ask every N s) and the strategies' signals
    on 1m candles built from the recorded trades (event-driven-backtester orders)
  → market-condition-simulator queue-fill   (--model queue and --model touch)
  → event-driven-backtester run --executions (P&L of the strategy orders per fill model)

Writes data/runtime/l2_fill_study.json. Everything measured is a simulation on recorded market
data; nothing here is a live or paper result.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ecosystem_tools import (  # noqa: E402
    indicators_json_to_candles_jsonl,
    project_root,
    resolve_cli,
    run_cli,
)
from strategy_validation import read_jsonl, shift_signals_to_bar_close, write_jsonl  # noqa: E402

logger = logging.getLogger(__name__)
STRATEGIES = ("rsi_mean_reversion", "macd_crossover")


def probe_orders(
    book_events: list[dict[str, Any]],
    *,
    symbol: str,
    every_seconds: int,
    quantity: str,
    tif_seconds: int,
) -> list[dict[str, Any]]:
    """A passive buy at the best bid and a passive sell at the best ask every N seconds."""
    bids: dict[Decimal, Decimal] = {}
    asks: dict[Decimal, Decimal] = {}
    synced = False
    next_at: datetime | None = None
    orders: list[dict[str, Any]] = []
    for event in book_events:
        kind = event.get("type")
        if kind == "book_snapshot":
            bids = {Decimal(p): Decimal(q) for p, q in event["bids"] if Decimal(q) > 0}
            asks = {Decimal(p): Decimal(q) for p, q in event["asks"] if Decimal(q) > 0}
            synced = True
        elif kind == "book_gap":
            synced = False
        elif kind == "book_diff" and synced:
            for levels, key in ((bids, "bids"), (asks, "asks")):
                for p, q in event[key]:
                    if Decimal(q) > 0:
                        levels[Decimal(p)] = Decimal(q)
                    else:
                        levels.pop(Decimal(p), None)
        if not synced or not bids or not asks or kind != "book_diff":
            continue
        now = datetime.fromisoformat(str(event["event_time"]))
        if next_at is None:
            next_at = now
        if now < next_at:
            continue
        next_at = now + timedelta(seconds=every_seconds)
        for side, price in (("buy", max(bids)), ("sell", min(asks))):
            orders.append(
                {
                    "order_id": f"probe-{len(orders)}",
                    "symbol": symbol,
                    "side": side,
                    "price": str(price),
                    "quantity": quantity,
                    "submitted_at": now.isoformat(),
                    "time_in_force_seconds": tif_seconds,
                }
            )
    return orders


def trades_to_ticks(book_events: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    return [
        {
            "exchange": "binance",
            "symbol": symbol,
            "trade_id": str(event.get("trade_id")),
            "price": str(event["price"]),
            "quantity": str(event["quantity"]),
            "side": str(event.get("side", "buy")),
            "event_time": str(event["event_time"]),
        }
        for event in book_events
        if event.get("type") == "trade"
    ]


def strategy_orders(
    ticks_path: Path, *, symbol: str, work: Path, quantity: str, tif_seconds: int
) -> tuple[Path, Path, dict[str, int]]:
    """1m candles from the recorded trades → indicators → signals → passive limit orders."""
    lake = work / "lake_1m"
    run_cli([resolve_cli("market-data-lakehouse"), "ingest", "--input", str(ticks_path),
             "--root", str(lake), "--exchange", "binance", "--symbol", symbol,
             "--timeframes", "1m", "--flush-batch-size", "5000"])
    query = run_cli([resolve_cli("market-data-lakehouse"), "query", "--root", str(lake),
                     "--symbol", symbol, "--timeframe", "1m", "--limit", "100000"])
    rows = sorted(json.loads(query.stdout), key=lambda r: str(r["open_time"]))
    candles = work / "candles_1m.jsonl"
    write_jsonl(candles, [
        {"symbol": symbol, "open": float(r["open"]), "high": float(r["high"]),
         "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"]),
         "event_time": str(r["open_time"]).replace(" ", "T")}
        for r in rows
    ])
    indicators = work / "indicators_1m.json"
    run_cli([resolve_cli("ta-indicators-from-scratch"), "compute", "--input", str(candles),
             "--indicator", "all", "--output", str(indicators)])
    enriched = work / "candles_1m_enriched.jsonl"
    indicators_json_to_candles_jsonl(indicators, enriched, event_times_source=candles)
    signals: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for strategy in STRATEGIES:
        out = work / f"signals_{strategy}.json"
        run_cli([resolve_cli("alpha-signal-generator"), "run", "--candles", str(enriched),
                 "--symbol", symbol, "--strategy", strategy, "--output", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        shifted = shift_signals_to_bar_close(payload, bar_seconds=60)
        counts[strategy] = len(shifted)
        signals += shifted
    signals.sort(key=lambda s: str(s["event_time"]))
    signals_path = work / "signals_1m.jsonl"
    write_jsonl(signals_path, signals)
    orders_path = work / "strategy_orders.jsonl"
    run_cli([resolve_cli("event-driven-backtester"), "orders", "--ticks", str(ticks_path),
             "--signals", str(signals_path), "--symbol", symbol, "--quantity", quantity,
             "--time-in-force-seconds", str(tif_seconds), "--output", str(orders_path)])
    return orders_path, signals_path, counts


def simulate(book: Path, orders: Path, *, symbol: str, model: str, work: Path,
             latency_ms: int) -> tuple[Path, dict[str, Any]]:
    fills = work / f"fills_{orders.stem}_{model}.jsonl"
    report = work / f"report_{orders.stem}_{model}.json"
    run_cli([resolve_cli("market-condition-simulator"), "queue-fill", "--book", str(book),
             "--orders", str(orders), "--symbol", symbol, "--model", model,
             "--latency-ms", str(latency_ms), "--output", str(fills), "--report", str(report)])
    summary = json.loads(report.read_text(encoding="utf-8"))
    summary.pop("outcomes", None)
    return fills, summary


def backtest(ticks: Path, signals: Path, *, symbol: str, quantity: str, work: Path,
             executions: Path | None, label: str) -> dict[str, Any]:
    out = work / f"backtest_{label}.json"
    command = [resolve_cli("event-driven-backtester"), "run", "--ticks", str(ticks),
               "--signals", str(signals), "--symbol", symbol, "--position-size", quantity,
               "--output", str(out)]
    if executions is not None:
        command += ["--executions", str(executions)]
    run_cli(command)
    result = json.loads(out.read_text(encoding="utf-8"))
    return {
        "fills": result["fill_count"],
        "rejected_fills": result.get("rejected_fills", 0),
        "final_equity": result["final_equity"],
        "pnl": str(Decimal(result["final_equity"]) - Decimal(result["initial_cash"])),
    }


def run_study(
    *,
    recordings: list[Path],
    symbol: str,
    probe_every_seconds: int = 30,
    probe_quantity: str = "0.001",
    tif_seconds: int = 60,
    latency_ms: int = 50,
) -> dict[str, Any]:
    work = project_root() / "data" / "runtime" / "work" / "l2_study"
    work.mkdir(parents=True, exist_ok=True)
    lake = project_root() / "data" / "lake"
    started = datetime.now(tz=UTC)

    ingest = run_cli([resolve_cli("market-data-lakehouse"), "ingest-depth", "--input",
                      *map(str, recordings), "--root", str(lake), "--symbol", symbol])
    first, last = _time_range(recordings)
    depth = work / "depth.jsonl"
    run_cli([resolve_cli("market-data-lakehouse"), "export-depth", "--root", str(lake),
             "--symbol", symbol, "--start", first, "--end", last, "--output", str(depth)])
    book = work / "book.jsonl"
    replay = run_cli([resolve_cli("order-book-reconstructor"), "replay", "--input", str(depth),
                      "--symbol", symbol, "--output", str(book)])
    replay_report = json.loads(replay.stdout)

    events = read_jsonl(book)
    probes = probe_orders(events, symbol=symbol, every_seconds=probe_every_seconds,
                          quantity=probe_quantity, tif_seconds=tif_seconds)
    probes_path = work / "probe_orders.jsonl"
    write_jsonl(probes_path, probes)
    ticks_path = work / "ticks.jsonl"
    write_jsonl(ticks_path, trades_to_ticks(events, symbol))
    orders_path, signals_path, signal_counts = strategy_orders(
        ticks_path, symbol=symbol, work=work, quantity=probe_quantity, tif_seconds=tif_seconds
    )

    results: dict[str, Any] = {"probe": {}, "strategy": {}}
    strategy_fills: dict[str, Path] = {}
    for model in ("queue", "touch"):
        _, results["probe"][model] = simulate(book, probes_path, symbol=symbol, model=model,
                                              work=work, latency_ms=latency_ms)
        fills, results["strategy"][model] = simulate(book, orders_path, symbol=symbol,
                                                     model=model, work=work,
                                                     latency_ms=latency_ms)
        strategy_fills[model] = fills

    pnl = {
        "immediate_market_fills": backtest(ticks_path, signals_path, symbol=symbol,
                                           quantity=probe_quantity, work=work, executions=None,
                                           label="immediate"),
        **{
            f"limit_{model}": backtest(ticks_path, signals_path, symbol=symbol,
                                       quantity=probe_quantity, work=work, executions=path,
                                       label=model)
            for model, path in strategy_fills.items()
        },
    }
    return {
        "kind": "simulation_on_recorded_data",
        "disclaimer": "Simulated fills on recorded Binance L2 data. Not live or paper results.",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "wall_seconds": (datetime.now(tz=UTC) - started).total_seconds(),
        "machine": f"{platform.system()} {platform.machine()} (python {platform.python_version()})",
        "symbol": symbol,
        "data": {"first_event": first, "last_event": last,
                 "lakehouse_ingest": json.loads(ingest.stdout), "replay": replay_report},
        "settings": {"latency_ms": latency_ms, "time_in_force_seconds": tif_seconds,
                     "probe_every_seconds": probe_every_seconds, "quantity": probe_quantity},
        "orders": {"probe": len(probes), "strategy": _count_lines(orders_path),
                   "strategy_signals": signal_counts},
        "fills": results,
        "strategy_pnl_usdt": pnl,
    }


def _count_lines(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _time_range(recordings: list[Path]) -> tuple[str, str]:
    stamps: list[str] = []
    for path in recordings:
        for record in read_jsonl(path):
            stamp = record.get("event_time") or record.get("received_at")
            if stamp:
                stamps.append(str(stamp))
    if not stamps:
        raise ValueError("recordings contain no timestamped records")
    return min(stamps), max(stamps)


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue-position vs touch fill study on L2 data")
    parser.add_argument("--recording", nargs="+", required=True, type=Path)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--probe-every-seconds", type=int, default=30)
    parser.add_argument("--quantity", default="0.001")
    parser.add_argument("--time-in-force-seconds", type=int, default=60)
    parser.add_argument("--latency-ms", type=int, default=50)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    report = run_study(
        recordings=args.recording,
        symbol=args.symbol.upper(),
        probe_every_seconds=args.probe_every_seconds,
        probe_quantity=args.quantity,
        tif_seconds=args.time_in_force_seconds,
        latency_ms=args.latency_ms,
    )
    output = project_root() / "data" / "runtime" / "l2_fill_study.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fills": report["fills"], "pnl": report["strategy_pnl_usdt"]}, indent=2))
    print(output)


if __name__ == "__main__":
    main()
