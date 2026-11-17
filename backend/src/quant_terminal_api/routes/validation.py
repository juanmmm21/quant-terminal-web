from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_settings
from quant_terminal_api.validation_gate import ValidationReportError, evaluate, load_report

router = APIRouter(prefix="/validation", tags=["validation"])


@router.get("")
async def validation_report(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
    timeframe: str = Query(default="1h"),
) -> dict[str, Any]:
    """Out-of-sample report (DSR, PBO, walk-forward, purged k-fold) and the gate verdict."""
    if timeframe not in settings.supported_timeframes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported timeframe: {timeframe}")
    try:
        report = load_report(settings.runtime_dir, timeframe)
    except ValidationReportError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"report": report, "gate": evaluate(report, settings.gate_policy()).as_dict()}
