from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from quant_terminal_api.models import BotStatus

logger = logging.getLogger(__name__)


class BotStateStore:
    """Thread-safe bot control state persisted to JSON for restart survival."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        self._lock = Lock()
        self._status = BotStatus.RUNNING
        self._updated_at = datetime.now(tz=UTC)
        self._message: str | None = None
        self._load()

    @property
    def status(self) -> BotStatus:
        with self._lock:
            return self._status

    @property
    def updated_at(self) -> datetime:
        with self._lock:
            return self._updated_at

    @property
    def message(self) -> str | None:
        with self._lock:
            return self._message

    def snapshot(self) -> tuple[BotStatus, datetime, str | None]:
        with self._lock:
            return self._status, self._updated_at, self._message

    def set_running(self, message: str | None = None) -> BotStatus:
        return self._transition(BotStatus.RUNNING, message or "bot resumed")

    def set_paused(self, message: str | None = None) -> BotStatus:
        return self._transition(BotStatus.PAUSED, message or "bot paused")

    def set_panic(self, reason: str) -> BotStatus:
        return self._transition(BotStatus.PANIC, reason)

    def _transition(self, status: BotStatus, message: str) -> BotStatus:
        with self._lock:
            self._status = status
            self._updated_at = datetime.now(tz=UTC)
            self._message = message
            self._persist()
            logger.info("bot state changed to %s: %s", status.value, message)
            return self._status

    def _load(self) -> None:
        if not self._state_path.exists():
            self._persist()
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("could not load bot state from %s: %s", self._state_path, exc)
            return
        if not isinstance(raw, dict):
            return
        status_raw = raw.get("status")
        updated_at_raw = raw.get("updated_at")
        try:
            if isinstance(status_raw, str):
                self._status = BotStatus(status_raw)
            if isinstance(updated_at_raw, str):
                self._updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
            message_raw = raw.get("message")
            if isinstance(message_raw, str):
                self._message = message_raw
        except ValueError as exc:
            logger.warning("invalid bot state file, using defaults: %s", exc)

    def _persist(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": self._status.value,
            "updated_at": self._updated_at.isoformat(),
            "message": self._message,
        }
        try:
            self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.error("failed to persist bot state: %s", exc)
