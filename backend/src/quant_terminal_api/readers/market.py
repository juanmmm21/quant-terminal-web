from __future__ import annotations

from pathlib import Path

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.models import CandlesResponse
from quant_terminal_api.readers.data import DataSourceError
from quant_terminal_api.readers.lakehouse import LakehouseCandlesReader, LakehouseError
from quant_terminal_api.readers.live_ticks import LiveTicksReader


class MarketCandlesProvider:
    """Combina velas del lakehouse con el último tick live (websocket-feed-handler → JSONL)."""

    def __init__(self, settings: TerminalSettings) -> None:
        self._settings = settings
        self._lakehouse = LakehouseCandlesReader(
            settings.lakehouse_root,
            settings.lakehouse_duckdb,
            symbol=settings.candle_symbol,
            timeframe=settings.candle_timeframe,
            limit=settings.candle_limit,
        )
        self._live_ticks = LiveTicksReader(settings.ticks_jsonl_path)

    def load(self) -> CandlesResponse:
        try:
            candles = self._lakehouse.load()
        except LakehouseError as exc:
            raise DataSourceError(str(exc)) from exc

        live_price = self._live_ticks.last_price()
        if live_price is not None:
            return candles.model_copy(update={"last_price": live_price})
        return candles


def lakehouse_is_ready(lakehouse_root: Path) -> bool:
    return lakehouse_root.exists() and any(lakehouse_root.rglob("candles.parquet"))
