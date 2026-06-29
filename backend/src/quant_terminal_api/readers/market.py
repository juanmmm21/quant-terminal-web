from __future__ import annotations

from pathlib import Path

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.models import CandlesResponse
from quant_terminal_api.readers.data import DataSourceError
from quant_terminal_api.readers.lakehouse import LakehouseCandlesReader, LakehouseError
from quant_terminal_api.readers.live_ticks import LiveTicksReader


class MarketCandlesProvider:
    """Combina velas del lakehouse con el último tick live (websocket-feed-handler → JSONL)."""

    def __init__(
        self,
        settings: TerminalSettings,
        *,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> None:
        self._settings = settings
        self._timeframe = timeframe or settings.default_timeframe
        self._limit = limit or settings.candle_limit
        self._live_ticks = LiveTicksReader(settings.ticks_jsonl_path)

    def load(self, *, timeframe: str | None = None, limit: int | None = None) -> CandlesResponse:
        from quant_terminal_api.readers.candle_aggregate import (
            aggregate_candles,
            dedupe_candles,
            resolve_lakehouse_timeframe,
        )

        requested = timeframe or self._timeframe
        candle_limit = limit or self._limit
        lake_tf, bucket_minutes = resolve_lakehouse_timeframe(requested)
        fetch_limit = candle_limit
        if bucket_minutes is not None:
            fetch_limit = min(candle_limit * bucket_minutes, 500_000)

        reader = LakehouseCandlesReader(
            self._settings.lakehouse_root,
            self._settings.lakehouse_duckdb,
            symbol=self._settings.candle_symbol,
            timeframe=lake_tf,
            limit=fetch_limit,
        )
        try:
            candles = reader.load()
        except LakehouseError as exc:
            raise DataSourceError(str(exc)) from exc

        if bucket_minutes is not None:
            aggregated = aggregate_candles(candles.candles, bucket_minutes=bucket_minutes)
            aggregated = dedupe_candles(aggregated)
            if len(aggregated) > candle_limit:
                aggregated = aggregated[-candle_limit:]
            last_close = aggregated[-1].close if aggregated else candles.last_price
            candles = candles.model_copy(
                update={
                    "interval": requested,
                    "candles": aggregated,
                    "last_price": last_close,
                }
            )
        else:
            deduped = dedupe_candles(candles.candles)
            if len(deduped) > candle_limit:
                deduped = deduped[-candle_limit:]
            candles = candles.model_copy(update={"interval": requested, "candles": deduped})

        live_price = self._live_ticks.last_price()
        if live_price is not None:
            return candles.model_copy(update={"last_price": live_price})
        return candles


def lakehouse_is_ready(lakehouse_root: Path) -> bool:
    return lakehouse_root.exists() and any(lakehouse_root.rglob("candles.parquet"))
