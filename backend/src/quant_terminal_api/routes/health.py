from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from quant_terminal_api import __version__
from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import (
    get_analysis_reader,
    get_bot_state,
    get_candles_reader,
    get_settings,
)
from quant_terminal_api.models import HealthResponse, TerminalSummaryResponse
from quant_terminal_api.readers import MarketCandlesProvider
from quant_terminal_api.readers.analysis import AnalysisCacheError, AnalysisCacheReader

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        timestamp=datetime.now(tz=UTC),
        data_mode=settings.data_mode,
    )


@router.get("/summary", response_model=TerminalSummaryResponse)
async def summary(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
    bot_state: Annotated[BotStateStore, Depends(get_bot_state)],
    candles_provider: Annotated[MarketCandlesProvider, Depends(get_candles_reader)],
    analysis_reader: Annotated[AnalysisCacheReader, Depends(get_analysis_reader)],
) -> TerminalSummaryResponse:
    timeframe = settings.default_timeframe
    candles = candles_provider.load(timeframe=timeframe, limit=settings.candle_limit)
    bot_status, _, _ = bot_state.snapshot()

    verdict = "hold"
    confidence = 0.0
    try:
        analysis = analysis_reader.load_snapshot(timeframe)
        verdict = analysis.recommendation.verdict
        confidence = analysis.recommendation.confidence
    except AnalysisCacheError:
        pass

    return TerminalSummaryResponse(
        data_mode=settings.data_mode,
        symbol=candles.symbol,
        last_price=candles.last_price,
        change_pct=candles.change_pct,
        recommendation_verdict=verdict,
        recommendation_confidence=confidence,
        analysis_timeframe=timeframe,
        bot_status=bot_status,
        last_sync=datetime.now(tz=UTC),
    )
