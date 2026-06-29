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
