from __future__ import annotations

from l2_fill_study import probe_orders, trades_to_ticks


def _diff(t: str, bids: list[list[str]], asks: list[list[str]]) -> dict[str, object]:
    return {"type": "book_diff", "event_time": t, "bids": bids, "asks": asks}


EVENTS: list[dict[str, object]] = [
    {"type": "book_snapshot", "event_time": "2026-11-17T23:00:00+00:00",
     "bids": [["100.00", "1"], ["99.99", "2"]], "asks": [["100.01", "3"]]},
    _diff("2026-11-17T23:00:00.100000+00:00", [["100.00", "0"]], []),
    {"type": "trade", "event_time": "2026-11-17T23:00:00.200000+00:00", "trade_id": 7,
     "price": "100.01", "quantity": "0.5", "side": "buy"},
    _diff("2026-11-17T23:00:10+00:00", [], [["100.02", "1"]]),
    {"type": "book_gap", "event_time": "2026-11-17T23:00:20+00:00"},
    _diff("2026-11-17T23:00:40+00:00", [["99.98", "1"]], []),
]


def test_probe_orders_join_the_touch_on_both_sides_only_while_synced() -> None:
    orders = probe_orders(EVENTS, symbol="BTCUSDT", every_seconds=5, quantity="0.001",
                          tif_seconds=60)
    assert [(o["side"], o["price"]) for o in orders] == [
        ("buy", "99.99"), ("sell", "100.01"),  # 100.00 was removed by the first diff
        ("buy", "99.99"), ("sell", "100.01"),
    ]
    assert all(o["time_in_force_seconds"] == 60 for o in orders)


def test_trades_become_ticks_for_the_backtester() -> None:
    ticks = trades_to_ticks(EVENTS, "BTCUSDT")
    assert ticks == [{"exchange": "binance", "symbol": "BTCUSDT", "trade_id": "7",
                      "price": "100.01", "quantity": "0.5", "side": "buy",
                      "event_time": "2026-11-17T23:00:00.200000+00:00"}]
