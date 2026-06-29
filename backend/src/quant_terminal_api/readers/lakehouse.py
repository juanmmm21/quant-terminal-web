from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import duckdb

from quant_terminal_api.models import CandleResponse, CandlesResponse

logger = logging.getLogger(__name__)


class LakehouseError(Exception):
    """Raised when lakehouse parquet data cannot be read."""


def _as_iso8601(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise LakehouseError("timestamp must be timezone-aware")
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            raise LakehouseError("timestamp must be timezone-aware")
        return parsed
    raise LakehouseError(f"unsupported timestamp type: {type(value)!r}")


class LakehouseCandlesReader:
    """Reads OHLCV candles from market-data-lakehouse Parquet via DuckDB (sin imports cruzados)."""

    def __init__(
        self,
        lakehouse_root: Path,
        duckdb_path: Path | None,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> None:
        self._lakehouse_root = lakehouse_root
        self._duckdb_path = duckdb_path or (lakehouse_root / "catalog.duckdb")
        self._symbol = symbol
        self._timeframe = timeframe
        self._limit = limit

    def load(self) -> CandlesResponse:
        if self._limit <= 0:
            raise ValueError("limit must be positive")
        if not self._lakehouse_root.exists():
            raise LakehouseError(
                f"lakehouse root not found: {self._lakehouse_root}. "
                "Run: python scripts/bootstrap_market_data.py"
            )

        parquet_files = [str(path) for path in self._lakehouse_root.rglob("candles.parquet")]
        if not parquet_files:
            raise LakehouseError(
                f"no candles.parquet under {self._lakehouse_root}. "
                "Run: python scripts/bootstrap_market_data.py"
            )

        self._duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(self._duckdb_path))
        try:
            paths_sql = ", ".join("'" + path.replace("'", "''") + "'" for path in parquet_files)
            connection.execute(
                f"""
                CREATE OR REPLACE VIEW candles AS
                SELECT * FROM read_parquet([{paths_sql}], union_by_name=true)
                """
            )
            rows = connection.execute(
                """
                SELECT open_time, open, high, low, close, volume
                FROM (
                    SELECT open_time, open, high, low, close, volume
                    FROM candles
                    WHERE symbol = ? AND timeframe = ?
                    ORDER BY open_time DESC
                    LIMIT ?
                )
                ORDER BY open_time ASC
                """,
                [self._symbol, self._timeframe, self._limit],
            ).fetchall()
        except duckdb.Error as exc:
            raise LakehouseError(f"duckdb query failed: {exc}") from exc
        finally:
            connection.close()

        if not rows:
            raise LakehouseError(
                f"no candles for {self._symbol} {self._timeframe} in lakehouse. "
                "Re-run bootstrap_market_data.py"
            )

        candles: list[CandleResponse] = []
        for row in rows:
            candles.append(
                CandleResponse(
                    open_time=_as_iso8601(row[0]),
                    open=str(row[1]),
                    high=str(row[2]),
                    low=str(row[3]),
                    close=str(row[4]),
                    volume=str(row[5]),
                )
            )

        last_price = candles[-1].close
        first_open = candles[0].open
        change_pct = "0"
        try:
            first_val = float(first_open)
            last_val = float(last_price)
            if first_val > 0:
                change_pct = str((last_val - first_val) / first_val)
        except ValueError:
            change_pct = "0"

        return CandlesResponse(
            symbol=self._symbol,
            interval=self._timeframe,
            currency="USDT",
            last_price=last_price,
            change_pct=change_pct,
            candles=candles,
        )
