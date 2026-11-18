"""Public, read-only endpoints for the paper-trading comparison page.

Only GET, no authentication, and only data meant to be published: the comparison written by
``scripts/paper_vs_backtest.py`` and a coarse liveness signal. No tokens, devices or controls.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_settings

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/paper")
async def public_paper(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
) -> dict[str, Any]:
    path = settings.paper_dir / "comparison.json"
    try:
        comparison: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "paper trading has not started yet") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "comparison unreadable") from exc
    heartbeat_age = None
    beat = settings.paper_dir / "heartbeat.json"
    if beat.exists():
        try:
            at = datetime.fromisoformat(json.loads(beat.read_text(encoding="utf-8"))["at"])
            heartbeat_age = (datetime.now(tz=UTC) - at).total_seconds()
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            heartbeat_age = None
    comparison["trader_alive"] = heartbeat_age is not None and heartbeat_age < 120
    comparison["heartbeat_age_seconds"] = heartbeat_age
    return comparison
