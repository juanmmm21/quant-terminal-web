from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_candles_reader, get_settings
from quant_terminal_api.models import CandlesResponse
from quant_terminal_api.readers import DataSourceError, MarketCandlesProvider

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/candles", response_model=CandlesResponse)
async def get_candles(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
    provider: Annotated[MarketCandlesProvider, Depends(get_candles_reader)],
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=10_000, ge=10, le=50_000),
) -> CandlesResponse:
    if timeframe not in settings.supported_timeframes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported timeframe: {timeframe}",
        )
    try:
        return provider.load(timeframe=timeframe, limit=limit)
    except (DataSourceError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
