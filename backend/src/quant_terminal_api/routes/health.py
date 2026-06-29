from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends

from quant_terminal_api import __version__
from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import (
    get_bot_state,
    get_candles_reader,
    get_equity_reader,
    get_metrics_reader,
    get_settings,
)
from quant_terminal_api.models import HealthResponse, TerminalSummaryResponse
from quant_terminal_api.readers import EquityReader, MarketCandlesProvider, MetricsReader

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
    equity_reader: Annotated[EquityReader, Depends(get_equity_reader)],
    metrics_reader: Annotated[MetricsReader, Depends(get_metrics_reader)],
) -> TerminalSummaryResponse:
    candles = candles_provider.load()
    equity = equity_reader.load()
    metrics = metrics_reader.load()
    bot_status, _, _ = bot_state.snapshot()

    initial = Decimal(equity.initial_capital)
    current = Decimal(equity.current_capital)
    capital_change = str(current - initial)

    return TerminalSummaryResponse(
        data_mode=settings.data_mode,
        symbol=candles.symbol,
        last_price=candles.last_price,
        account_capital=equity.current_capital,
        capital_change=capital_change,
        trade_count=metrics.trade_count,
        bot_status=bot_status,
        last_sync=datetime.now(tz=UTC),
    )
