from __future__ import annotations

import os
from pathlib import Path

from market_daemon import TickTail, write_tick_delta


def test_tail_reads_only_new_complete_lines_and_follows_rotation(tmp_path: Path) -> None:
    ticks = tmp_path / "ticks.jsonl"
    ticks.write_text('{"a":1}\n', encoding="utf-8")
    tail = TickTail(ticks)  # starts at the end: history is already in the lakehouse
    assert tail.read_new() == []
    with ticks.open("a", encoding="utf-8") as handle:
        handle.write('{"a":2}\n{"a":3')  # last line still being written
    assert tail.read_new() == ['{"a":2}']
    with ticks.open("a", encoding="utf-8") as handle:
        handle.write('}\n{"a":4}\n')
    os.replace(ticks, tmp_path / "ticks.jsonl.1")  # the writer rotates...
    ticks.write_text('{"a":5}\n', encoding="utf-8")  # ...and starts a new file
    assert tail.read_new() == ['{"a":3}', '{"a":4}', '{"a":5}']
    staging = tmp_path / "delta.jsonl"
    with ticks.open("a", encoding="utf-8") as handle:
        handle.write('{"a":6}\n')
    assert write_tick_delta(tail, staging) == 1
    assert staging.read_text(encoding="utf-8") == '{"a":6}\n'
