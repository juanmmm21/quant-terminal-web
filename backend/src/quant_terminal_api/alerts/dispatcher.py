"""``quant-alerts``: push new journal alerts to every registered device.

Reads ``events.jsonl`` and ``fills.jsonl`` incrementally (the offsets survive restarts in
``alerts_state.json``), keeps alerts at or above ``TERMINAL_ALERTS_MIN_SEVERITY`` and sends each
one to every active device with a push token. Tokens APNs reports as gone are cleared. Without
APNs configuration the process only advances its offsets, so it never replays old alerts later.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Any

from quant_terminal_api.alerts.apns import ApnsClient
from quant_terminal_api.alerts.catalog import SEVERITY_ORDER, Alert, from_event, from_fill
from quant_terminal_api.auth import DeviceRegistry
from quant_terminal_api.config import TerminalSettings

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(self, paper_dir: Path, registry: DeviceRegistry, client: ApnsClient | None,
                 *, min_severity: str = "warning") -> None:
        self._paper_dir = paper_dir
        self._registry = registry
        self._client = client
        self._min = SEVERITY_ORDER[min_severity]
        self._state_path = paper_dir / "alerts_state.json"
        self._offsets: dict[str, int] = {"events.jsonl": 0, "fills.jsonl": 0}
        if self._state_path.exists():
            self._offsets.update(json.loads(self._state_path.read_text(encoding="utf-8")))

    def _new_lines(self, name: str) -> list[dict[str, Any]]:
        path = self._paper_dir / name
        if not path.exists():
            return []
        with path.open("rb") as handle:
            size = handle.seek(0, 2)
            if size < self._offsets[name]:
                self._offsets[name] = 0  # file replaced
            handle.seek(self._offsets[name])
            chunk = handle.read()
        complete = chunk[: chunk.rfind(b"\n") + 1]
        self._offsets[name] += len(complete)
        rows = []
        for line in complete.decode("utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def poll(self) -> list[tuple[Alert, int]]:
        """Send what is new; returns (alert, devices reached)."""
        alerts = [a for a in (from_event(r) for r in self._new_lines("events.jsonl")) if a]
        alerts += [from_fill(r) for r in self._new_lines("fills.jsonl")]
        delivered: list[tuple[Alert, int]] = []
        for alert in alerts:
            if SEVERITY_ORDER[alert.severity] < self._min:
                continue
            reached = 0
            if self._client is not None:
                for device_id, token, environment in self._registry.push_targets():
                    result = self._client.send(token, alert.as_dict(), environment=environment,
                                               critical=alert.severity == "critical")
                    if result.status == 200:
                        reached += 1
                    elif result.device_gone:
                        self._registry.clear_push_token(device_id)
            delivered.append((alert, reached))
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._offsets), encoding="utf-8")
        os.replace(tmp, self._state_path)
        return delivered


def client_from_settings(settings: TerminalSettings) -> ApnsClient | None:
    if not (settings.apns_key_path and settings.apns_key_id and settings.apns_team_id
            and settings.apns_topic):
        return None
    return ApnsClient(key_path=settings.apns_key_path, key_id=settings.apns_key_id,
                      team_id=settings.apns_team_id, topic=settings.apns_topic)


def main() -> None:
    parser = argparse.ArgumentParser(description="Push paper-trading alerts to iOS devices")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--min-severity", default=os.environ.get(
        "TERMINAL_ALERTS_MIN_SEVERITY", "warning"), choices=list(SEVERITY_ORDER))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    settings = TerminalSettings().resolve_paths()
    client = client_from_settings(settings)
    if client is None:
        logger.warning("APNs not configured: alerts are tracked but not pushed")
    settings.paper_dir.mkdir(parents=True, exist_ok=True)
    dispatcher = AlertDispatcher(settings.paper_dir, DeviceRegistry(settings.devices_path),
                                 client, min_severity=args.min_severity)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            for alert, reached in dispatcher.poll():
                logger.info("alert %s (%s) pushed to %s devices", alert.kind, alert.severity,
                            reached)
        except Exception:
            logger.exception("alert dispatch failed")
        stop.wait(args.interval_seconds)


if __name__ == "__main__":
    main()
