#!/usr/bin/env python3
"""Build samples/audit.db from audit_events.jsonl (trade-audit-logger compatible schema)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def main() -> None:
    samples_dir = Path(__file__).resolve().parent
    jsonl_path = samples_dir / "audit_events.jsonl"
    db_path = samples_dir / "audit.db"

    if not jsonl_path.exists():
        raise SystemExit(f"missing input: {jsonl_path}")

    connection = sqlite3.connect(db_path)
    connection.executescript(SCHEMA)
    connection.execute("DELETE FROM audit_events")

    recorded_at = datetime.now(tz=UTC).isoformat()
    inserted = 0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        connection.execute(
            """
            INSERT INTO audit_events (
                event_id, event_type, symbol, correlation_id,
                occurred_at, recorded_at, severity, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["event_type"],
                event["symbol"],
                event["correlation_id"],
                event["occurred_at"],
                recorded_at,
                event["severity"],
                json.dumps(event["payload"]),
            ),
        )
        inserted += 1
    connection.commit()
    connection.close()
    print(f"built {db_path} with {inserted} events")


if __name__ == "__main__":
    main()
