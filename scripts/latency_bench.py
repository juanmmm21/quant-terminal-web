#!/usr/bin/env python3
"""
Tick-to-decision latency on recorded Binance L2 data, before and after the Rust accelerators.

Every recorded depth diff is turned back into the raw Binance message and pushed through a full
path that ends in the same trading decision (top-5 microprice and imbalance, in Decimal):

  baseline  json.loads → BinanceDepthDiffParser (Decimal) → DepthSynchronizer → view(5) → decide
  fast-py   websocket_feed_handler.fast (Python) → FastOrderBook (Python levels) → decide
  fast-rs   websocket_feed_handler.fast (Rust)   → FastOrderBook (Rust levels)   → decide

The decision of every message is compared across the three paths; any difference aborts the run.
Latency is measured with perf_counter_ns around each message, after a warm-up.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import sys
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

Decision = tuple[str, str, str] | None


def decide(bids: list[tuple[Decimal, Decimal]], asks: list[tuple[Decimal, Decimal]]) -> Decision:
    """Top-5 imbalance and the microprice; the signal a market maker would act on."""
    if not bids or not asks:
        return None
    bid_depth = sum((q for _, q in bids[:5]), Decimal("0"))
    ask_depth = sum((q for _, q in asks[:5]), Decimal("0"))
    (bid, bid_q), (ask, ask_q) = bids[0], asks[0]
    micro = (bid * ask_q + ask * bid_q) / (bid_q + ask_q)
    imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
    signal = "lean_bid" if imbalance > Decimal("0.2") else (
        "lean_ask" if imbalance < Decimal("-0.2") else "flat"
    )
    return signal, f"{micro:.6f}", f"{imbalance:.6f}"


def _plain(value: str) -> str:
    """Recordings made before websocket-feed-handler 9d5cda4 wrote Binance's "0.00000000" as
    "0E-8"; restore the exchange's fixed-point text."""
    return format(Decimal(value), "f") if "E" in value else value


def load_messages(recording: Path, limit: int | None) -> tuple[dict[str, Any], list[str]]:
    snapshot: dict[str, Any] | None = None
    messages: list[str] = []
    rows = [json.loads(line) for line in recording.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    rows.sort(key=lambda r: str(r.get("received_at") or r.get("event_time")))
    for row in rows:
        if row.get("type") == "depth_snapshot" and snapshot is None:
            snapshot = row
        elif row.get("type") == "depth_diff" and snapshot is not None:
            if row["final_update_id"] <= snapshot["last_update_id"]:
                continue
            event_ms = int(datetime.fromisoformat(row["event_time"]).timestamp() * 1000)
            row["bids"] = [[_plain(p), _plain(q)] for p, q in row["bids"]]
            row["asks"] = [[_plain(p), _plain(q)] for p, q in row["asks"]]
            messages.append(json.dumps({
                "stream": "btcusdt@depth@100ms",
                "data": {"e": "depthUpdate", "E": event_ms, "s": row["symbol"],
                         "U": row["first_update_id"], "u": row["final_update_id"],
                         "b": row["bids"], "a": row["asks"]},
            }, separators=(",", ":")))
        if limit and len(messages) >= limit:
            break
    if snapshot is None:
        raise SystemExit("the recording has no depth snapshot")
    return snapshot, messages


def baseline_path(snapshot: dict[str, Any]) -> Callable[[str], Decision]:
    """What v0.1 did per message: json.loads, Decimal parsing, sequence check, book, view."""
    from order_book_reconstructor.exchanges.binance import BinanceDepthParser
    from order_book_reconstructor.models import BookSnapshot, DepthUpdate, ExchangeId, PriceLevel
    from order_book_reconstructor.reconstructor import OrderBookReconstructor
    from order_book_reconstructor.sync import DepthSynchronizer, DiffOutcome

    parser = BinanceDepthParser()
    sync = DepthSynchronizer(OrderBookReconstructor(ExchangeId.BINANCE, "BTCUSDT"))
    sync.on_snapshot(BookSnapshot(
        ExchangeId.BINANCE, "BTCUSDT",
        tuple(PriceLevel(Decimal(p), Decimal(q)) for p, q in snapshot["bids"] if Decimal(q)),
        tuple(PriceLevel(Decimal(p), Decimal(q)) for p, q in snapshot["asks"] if Decimal(q)),
        int(snapshot["last_update_id"]),
    ))

    def step(raw: str) -> Decision:
        update = parser.parse(json.loads(raw)["data"])
        assert isinstance(update, DepthUpdate)
        if sync.on_diff(update) is not DiffOutcome.APPLIED:
            return None
        view = sync.book.view(5)
        return decide([(lv.price, lv.quantity) for lv in view.bids],
                      [(lv.price, lv.quantity) for lv in view.asks])

    return step


def fast_path(snapshot: dict[str, Any], backend: str) -> Callable[[str], Decision]:
    from order_book_reconstructor.fast import FastOrderBook
    from order_book_reconstructor.sync import DiffOutcome
    from websocket_feed_handler import fast

    parse = fast.parse_depth_raw if backend == "rust" else fast.py_parse_depth
    if backend == "rust" and fast.BACKEND != "rust":
        raise SystemExit("websocket-feed-handler-rs is not installed")
    book = FastOrderBook(backend)
    book.load_snapshot(int(snapshot["last_update_id"]),
                       [tuple(x) for x in snapshot["bids"]], [tuple(x) for x in snapshot["asks"]])

    def step(raw: str) -> Decision:
        parsed = parse(raw)
        assert parsed is not None
        _, first, final, _, bids, asks = parsed
        if book.apply_diff(first, final, bids, asks) is not DiffOutcome.APPLIED:
            return None
        top_bids, top_asks = book.levels.top(5)
        return decide([(Decimal(p), Decimal(q)) for p, q in top_bids],
                      [(Decimal(p), Decimal(q)) for p, q in top_asks])

    return step


def run(step: Callable[[str], Decision], messages: list[str], warmup: int) -> tuple[
        list[int], list[Decision]]:
    decisions: list[Decision] = []
    latencies: list[int] = []
    gc.collect()
    for index, raw in enumerate(messages):
        start = time.perf_counter_ns()
        decision = step(raw)
        elapsed = time.perf_counter_ns() - start
        decisions.append(decision)
        if index >= warmup:
            latencies.append(elapsed)
    return latencies, decisions


def summary(latencies: list[int]) -> dict[str, float]:
    ordered = sorted(latencies)

    def pct(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(p * len(ordered)))] / 1000.0

    return {"n": len(ordered), "mean_us": statistics.fmean(ordered) / 1000.0, "p50_us": pct(0.5),
            "p90_us": pct(0.9), "p99_us": pct(0.99), "p999_us": pct(0.999),
            "max_us": ordered[-1] / 1000.0}


BUCKETS_US = (2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10_000)


def histogram(latencies: list[int]) -> list[tuple[str, int]]:
    counts = [0] * (len(BUCKETS_US) + 1)
    for value in latencies:
        us = value / 1000.0
        index = next((i for i, edge in enumerate(BUCKETS_US) if us < edge), len(BUCKETS_US))
        counts[index] += 1
    labels = [f"<{edge}µs" for edge in BUCKETS_US] + [f">={BUCKETS_US[-1]}µs"]
    return list(zip(labels, counts, strict=True))


def render(name: str, latencies: list[int]) -> str:
    rows = histogram(latencies)
    peak = max(count for _, count in rows) or 1
    lines = [f"{name}"]
    for label, count in rows:
        if count:
            lines.append(f"  {label:>9} {count:7d} {'#' * max(1, round(40 * count / peak))}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tick-to-decision latency, Python vs Rust")
    parser.add_argument("--recording", nargs="+", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--warmup", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    merged = Path("/tmp") / f"latency_bench_{int(time.time())}.jsonl"
    merged.write_text("".join(p.read_text(encoding="utf-8") for p in args.recording),
                      encoding="utf-8")
    snapshot, messages = load_messages(merged, args.limit)
    merged.unlink()
    paths = {
        "baseline (v0.1, Decimal objects)": baseline_path(snapshot),
        "fast API, Python fallback": fast_path(snapshot, "python"),
        "fast API, Rust accelerators": fast_path(snapshot, "rust"),
    }
    results: dict[str, Any] = {}
    reference: list[Decision] | None = None
    for name, step in paths.items():
        latencies, decisions = run(step, messages, args.warmup)
        if reference is None:
            reference = decisions
        elif decisions != reference:
            first = next(i for i, (a, b) in enumerate(zip(decisions, reference, strict=True))
                         if a != b)
            raise SystemExit(f"{name} decided differently at message {first}")
        results[name] = summary(latencies)
        print(render(name, latencies), file=sys.stderr)
    report = {
        "messages": len(messages),
        "warmup": args.warmup,
        "decisions_identical": True,
        "machine": f"{platform.system()} {platform.machine()}, {platform.processor() or 'cpu'}, "
                   f"Python {platform.python_version()}",
        "results": results,
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
