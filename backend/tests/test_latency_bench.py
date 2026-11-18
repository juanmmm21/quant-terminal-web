from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from latency_bench import baseline_path, decide, fast_path, histogram, load_messages, run

pytest.importorskip("order_book_reconstructor.fast")


def test_decide_is_the_microprice_and_imbalance_signal() -> None:
    bids = [(Decimal("100"), Decimal("3")), (Decimal("99"), Decimal("1"))]
    asks = [(Decimal("101"), Decimal("1"))]
    assert decide(bids, asks) == ("lean_bid", "100.750000", "0.600000")
    assert decide([], asks) is None


def test_histogram_buckets() -> None:
    labels = dict(histogram([1_500, 15_000, 15_000_000]))
    assert labels["<2µs"] == 1 and labels["<20µs"] == 1 and labels[">=10000µs"] == 1


def _recording(tmp_path: Path) -> Path:
    rows = [{"type": "depth_snapshot", "last_update_id": 10, "received_at": "2026-11-18T00:00:00",
             "bids": [["100.00", "1.00000000"]], "asks": [["101.00", "2.00000000"]]}]
    for i in range(11, 60):
        rows.append({"type": "depth_diff", "symbol": "BTCUSDT", "first_update_id": i,
                     "final_update_id": i, "event_time": "2026-11-18T00:00:01+00:00",
                     "received_at": f"2026-11-18T00:00:{i:02d}",
                     "bids": [["100.00", f"{i}.00000000"], ["99.50", "0E-8"]],
                     "asks": [["101.00", "1.00000000"]]})
    path = tmp_path / "rec.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def test_all_paths_reach_identical_decisions(tmp_path: Path) -> None:
    snapshot, messages = load_messages(_recording(tmp_path), None)
    assert len(messages) == 49 and '"0.00000000"' in messages[0]
    _, reference = run(baseline_path(snapshot), messages, warmup=0)
    _, python = run(fast_path(snapshot, "python"), messages, warmup=0)
    assert python == reference and reference[-1] is not None
    try:
        _, rust = run(fast_path(snapshot, "rust"), messages, warmup=0)
    except SystemExit:
        pytest.skip("Rust accelerators not installed")
    assert rust == reference
