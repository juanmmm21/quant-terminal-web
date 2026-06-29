from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BotStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    PANIC = "panic"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    timestamp: datetime
    data_mode: str = "demo"


class TerminalSummaryResponse(BaseModel):
    data_mode: str
    symbol: str
    last_price: str
    price_currency: str = "USDT"
    change_pct: str = "0"
    recommendation_verdict: str = "hold"
    recommendation_confidence: float = 0.0
    analysis_timeframe: str = "1h"
    bot_status: BotStatus
    last_sync: datetime


class BotStatusResponse(BaseModel):
    status: BotStatus
    updated_at: datetime
    message: str | None = None


class BotActionResponse(BaseModel):
    status: BotStatus
    updated_at: datetime
    action: str
    message: str


class PerformanceMetricsResponse(BaseModel):
    symbol: str
    sharpe_ratio: str
    sortino_ratio: str
    profit_factor: str
    max_drawdown_pct: str
    total_return_pct: str
    win_rate: str
    trade_count: int
    computed_at: datetime | None = None


class EquityPointResponse(BaseModel):
    event_time: datetime
    equity: str


class EquityCurveResponse(BaseModel):
    symbol: str
    currency: str = "USDT"
    label: str = "Capital de la cuenta"
    initial_capital: str
    current_capital: str
    points: list[EquityPointResponse]


class AuditEventResponse(BaseModel):
    event_id: str
    event_type: str
    symbol: str
    correlation_id: str
    occurred_at: datetime
    severity: str
    payload: dict[str, Any]


class AuditEventsResponse(BaseModel):
    events: list[AuditEventResponse]
    count: int


class ErrorResponse(BaseModel):
    detail: str


class PanicRequest(BaseModel):
    reason: str = Field(default="manual_panic", min_length=1, max_length=500)


class CandleResponse(BaseModel):
    open_time: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str


class CandlesResponse(BaseModel):
    symbol: str
    interval: str
    currency: str = "USDT"
    last_price: str
    change_pct: str
    candles: list[CandleResponse]


class TradeFillResponse(BaseModel):
    order_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    commission: str
    filled_at: datetime
    realized_pnl: str | None = None
    label: str | None = None


class TradesResponse(BaseModel):
    trades: list[TradeFillResponse]
    count: int
    closed_round_trips: int


class EcosystemStatusResponse(BaseModel):
    data_mode: str
    ecosystem_ready: bool
    lakehouse_ready: bool
    live_ticks_ready: bool
    analysis_ready: bool
    paths: dict[str, str]
    modules: dict[str, str]
    manifest: dict[str, Any] | None = None
    last_checked: datetime


class RecommendationResponse(BaseModel):
    verdict: str
    action: str
    side: str | None = None
    confidence: float
    reason: str
    strategy_id: str
    reference_price: str
    event_time: datetime | None = None


class IndicatorSnapshotResponse(BaseModel):
    rsi: float | None = None
    macd_line: float | None = None
    signal_line: float | None = None
    sma_20: float | None = None
    ema_20: float | None = None


class TrainingStatsResponse(BaseModel):
    timeframe: str
    symbol: str
    bars_analyzed: int
    signal_count: int
    enter_signals: int
    exit_signals: int
    directional_win_rate: str
    selected_strategy: str
    trained_at: datetime


class SignalMarkerResponse(BaseModel):
    event_time: datetime
    action: str
    side: str | None = None
    confidence: float
    reason: str
    reference_price: str
    strategy_id: str


class AnalysisSnapshotResponse(BaseModel):
    symbol: str
    timeframe: str
    last_price: str
    currency: str = "USDT"
    updated_at: datetime
    recommendation: RecommendationResponse
    indicators: IndicatorSnapshotResponse
    training: TrainingStatsResponse
    signals: list[SignalMarkerResponse]
