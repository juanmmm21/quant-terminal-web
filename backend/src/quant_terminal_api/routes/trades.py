from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from quant_terminal_api.dependencies import get_trades_reader
from quant_terminal_api.models import TradesResponse
from quant_terminal_api.readers import DataSourceError, TradesReader

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("", response_model=TradesResponse)
async def list_trades(
    reader: Annotated[TradesReader, Depends(get_trades_reader)],
) -> TradesResponse:
    try:
        return reader.load()
    except DataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
