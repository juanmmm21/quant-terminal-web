"""Durable paper-trading state: write-ahead intents, fills ledger and equity snapshots.

Files under ``data/paper/`` (one directory per deployment):

* ``state.json``   position, cash, sequence, pending intents, kill/halt flags (atomic writes)
* ``fills.jsonl``  every booked fill, exactly once (keyed by client order id)
* ``equity.jsonl`` equity marked to the last price at every step
* ``events.jsonl`` decisions and incidents (halts, rejections, reconciliations)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PaperState:
    initial_cash: str = "10000"
    cash: str = "10000"
    position: str = "0"
    average_price: str = "0"
    sequence: int = 0
    pending: dict[str, dict[str, str]] = field(default_factory=dict)
    booked: list[str] = field(default_factory=list)
    kill_pending: bool = False
    halted_reason: str | None = None
    last_step_at: str | None = None
    peak_equity_day: str | None = None
    peak_equity: str = "0"
    started_at: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())


class PaperJournal:
    def __init__(self, directory: Path, *, initial_cash: Decimal = Decimal("10000")) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self._state_path = directory / "state.json"
        self.state = self._load(initial_cash)

    def _load(self, initial_cash: Decimal) -> PaperState:
        if self._state_path.exists():
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            return PaperState(**raw)
        state = PaperState(initial_cash=str(initial_cash), cash=str(initial_cash))
        self._write_state(state)
        return state

    def save(self) -> None:
        self._write_state(self.state)

    def _write_state(self, state: PaperState) -> None:
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._state_path)

    def append(self, name: str, record: dict[str, Any]) -> None:
        with (self.directory / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def event(self, kind: str, **details: Any) -> None:
        self.append("events.jsonl", {"at": datetime.now(tz=UTC).isoformat(), "kind": kind,
                                     **details})

    def read(self, name: str) -> list[dict[str, Any]]:
        path = self.directory / name
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
