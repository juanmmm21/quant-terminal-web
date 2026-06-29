from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from quant_terminal_api.dependencies import get_equity_reader, get_metrics_reader
from quant_terminal_api.models import EquityCurveResponse, PerformanceMetricsResponse
from quant_terminal_api.readers import DataSourceError, EquityReader, MetricsReader

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=PerformanceMetricsResponse)
async def get_metrics(
    reader: Annotated[MetricsReader, Depends(get_metrics_reader)],
) -> PerformanceMetricsResponse:
    try:
        return reader.load()
    except DataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/equity-curve", response_model=EquityCurveResponse)
async def get_equity_curve(
    reader: Annotated[EquityReader, Depends(get_equity_reader)],
) -> EquityCurveResponse:
    try:
        symbol, points = reader.load()
    except DataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return EquityCurveResponse(symbol=symbol, points=points)
