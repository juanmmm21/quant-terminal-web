"""``GET /mobile/overview``: everything the iOS app shows, in one authenticated call."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from quant_terminal_api.alerts.catalog import read_jsonl, recent_alerts
from quant_terminal_api.auth import Principal, require_control
from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_bot_state, get_settings

router = APIRouter(prefix="/mobile", tags=["mobile"])


def _json(path: Any) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _dec(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


@router.get("/overview")
async def overview(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
    store: Annotated[BotStateStore, Depends(get_bot_state)],
    _principal: Annotated[Principal, Depends(require_control)],
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    bot_status, updated_at, message = store.snapshot()
    paper = settings.paper_dir
    heartbeat = _json(paper / "heartbeat.json") or {}
    state = _json(paper / "state.json") or {}
    promotion = _json(settings.promotion_path)
    equity_rows = read_jsonl(paper / "equity.jsonl")[-200:]

    age = None
    if heartbeat.get("at"):
        age = (now - datetime.fromisoformat(str(heartbeat["at"]))).total_seconds()
    initial = _dec(state.get("initial_cash"), "10000")
    last = equity_rows[-1] if equity_rows else None
    equity = _dec(last["equity"]) if last else initial
    return {
        "generated_at": now.isoformat(),
        "bot": {"status": bot_status.value, "message": message,
                "updated_at": updated_at.isoformat()},
        "trader": {
            "alive": age is not None and age < 120,
            "heartbeat_age_seconds": age,
            "venue": heartbeat.get("venue"),
            "last_action": heartbeat.get("action"),
            "halted_reason": heartbeat.get("halted_reason"),
            "kill_pending": bool(heartbeat.get("kill_pending")),
        },
        "strategy": None if not promotion or not promotion.get("active") else {
            "name": promotion.get("strategy"), "timeframe": promotion.get("timeframe"),
            "symbol": promotion.get("symbol"), "gate_passed": promotion.get("gate_passed"),
            "promoted_at": promotion.get("promoted_at"),
        },
        "pnl": {
            "currency": "USDT",
            "initial_equity": format(initial, "f"),
            "equity": format(equity, "f"),
            "pnl": format(equity - initial, "f"),
            "return_pct": float((equity - initial) / initial) if initial else 0.0,
            "position": state.get("position", "0"),
            "last_price": last.get("price") if last else None,
            "equity_curve": [{"at": r["at"], "equity": r["equity"]} for r in equity_rows],
        },
        "alerts": [alert.as_dict() for alert in recent_alerts(paper)],
        "disclaimer": "Paper trading on the Binance testnet: test funds, not real money.",
    }
