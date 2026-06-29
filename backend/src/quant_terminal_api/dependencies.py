from __future__ import annotations

from typing import cast

from fastapi import Request

from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.readers import (
    AuditReader,
    EquityReader,
    MarketCandlesProvider,
    MetricsReader,
    TradesReader,
)


def get_settings(request: Request) -> TerminalSettings:
    return cast(TerminalSettings, request.app.state.settings)


def get_bot_state(request: Request) -> BotStateStore:
    return cast(BotStateStore, request.app.state.bot_state)


def get_audit_reader(request: Request) -> AuditReader:
    settings: TerminalSettings = request.app.state.settings
    return AuditReader(settings.audit_db_path)


def get_metrics_reader(request: Request) -> MetricsReader:
    settings: TerminalSettings = request.app.state.settings
    return MetricsReader(settings.metrics_path)


def get_equity_reader(request: Request) -> EquityReader:
    settings: TerminalSettings = request.app.state.settings
    return EquityReader(settings.equity_path)


def get_candles_reader(request: Request) -> MarketCandlesProvider:
    settings: TerminalSettings = request.app.state.settings
    return MarketCandlesProvider(settings)


def get_trades_reader(request: Request) -> TradesReader:
    settings: TerminalSettings = request.app.state.settings
    return TradesReader(settings.trades_path)
