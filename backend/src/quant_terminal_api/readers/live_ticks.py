from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LiveTicksReader:
    """Lee el último tick de un JSONL alimentado por websocket-feed-handler / tick_bridge."""

    def __init__(self, ticks_path: Path) -> None:
        self._ticks_path = ticks_path

    def last_price(self) -> str | None:
        if not self._ticks_path.exists():
            return None
        try:
            lines = self._ticks_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("could not read ticks file %s: %s", self._ticks_path, exc)
            return None

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            price = payload.get("price")
            if isinstance(price, str):
                return price
            if isinstance(price, (int, float)):
                return str(price)
        return None
