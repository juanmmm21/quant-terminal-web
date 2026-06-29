from __future__ import annotations

from functools import lru_cache

from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.readers import AuditReader, EquityReader, MetricsReader


@lru_cache
def get_settings() -> TerminalSettings:
    return TerminalSettings().resolve_paths()


def get_bot_state() -> BotStateStore:
    settings = get_settings()
    return BotStateStore(settings.bot_state_path)


def get_audit_reader() -> AuditReader:
    settings = get_settings()
    return AuditReader(settings.audit_db_path)


def get_metrics_reader() -> MetricsReader:
    settings = get_settings()
    return MetricsReader(settings.metrics_path)


def get_equity_reader() -> EquityReader:
    settings = get_settings()
    return EquityReader(settings.equity_path)
