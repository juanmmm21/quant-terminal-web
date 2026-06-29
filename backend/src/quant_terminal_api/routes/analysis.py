from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_analysis_reader, get_settings
from quant_terminal_api.models import AnalysisSnapshotResponse
from quant_terminal_api.readers.analysis import AnalysisCacheError, AnalysisCacheReader

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/snapshot", response_model=AnalysisSnapshotResponse)
async def analysis_snapshot(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
    reader: Annotated[AnalysisCacheReader, Depends(get_analysis_reader)],
    timeframe: str = Query(default="1h"),
) -> AnalysisSnapshotResponse:
    if timeframe not in settings.supported_timeframes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported timeframe: {timeframe}",
        )
    try:
        return reader.load_snapshot(timeframe)
    except AnalysisCacheError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
