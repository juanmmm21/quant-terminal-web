from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from quant_terminal_api.dependencies import get_candles_reader
from quant_terminal_api.models import CandlesResponse
from quant_terminal_api.readers import DataSourceError, MarketCandlesProvider

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/candles", response_model=CandlesResponse)
async def get_candles(
    provider: Annotated[MarketCandlesProvider, Depends(get_candles_reader)],
) -> CandlesResponse:
    try:
        return provider.load()
    except DataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
