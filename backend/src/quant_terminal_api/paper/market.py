"""What the trader knows about the market, and whether it is fresh enough to act on."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MarketView:
    price: Decimal | None
    stale: bool
    reason: str


def _tail_price(path: Path) -> tuple[Decimal | None, datetime | None]:
    if not path.exists():
        return None, None
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 8192))
        lines = handle.read().decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("price") is not None:
            stamp = record.get("event_time")
            moment = None
            if isinstance(stamp, str):
                moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            return Decimal(str(record["price"])), moment
    return None, None


def read_market(
    ticks_path: Path,
    status_path: Path,
    *,
    now: datetime | None = None,
    max_tick_age_seconds: float = 30.0,
    max_status_age_seconds: float = 10.0,
) -> MarketView:
    """Fresh only if the feed says so *and* its status file and last tick are recent.

    A dead feed process stops updating its status file, so an old status file is stale too.
    """
    current = now or datetime.now(tz=UTC)
    price, tick_time = _tail_price(ticks_path)
    if not status_path.exists():
        return MarketView(price, True, "feed status file missing")
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(str(status["checked_at"]).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return MarketView(price, True, "feed status unreadable")
    if (current - checked).total_seconds() > max_status_age_seconds:
        return MarketView(price, True, "feed status not updated (feed process down?)")
    if status.get("stale"):
        return MarketView(price, True, "feed reports stale data")
    if price is None or tick_time is None:
        return MarketView(price, True, "no tick yet")
    if (current - tick_time).total_seconds() > max_tick_age_seconds:
        return MarketView(price, True, "last tick too old")
    return MarketView(price, False, "fresh")
