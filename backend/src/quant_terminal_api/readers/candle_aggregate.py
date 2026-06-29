from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quant_terminal_api.models import CandleResponse


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def aggregate_candles(
    candles: list[CandleResponse],
    *,
    bucket_minutes: int,
) -> list[CandleResponse]:
    """Agrupa velas base (p. ej. 1m) en marcos mayores no nativos del lakehouse (10m, 15m)."""
    if bucket_minutes <= 1 or not candles:
        return candles

    bucket_seconds = bucket_minutes * 60
    sorted_candles = sorted(candles, key=lambda candle: candle.open_time)
    buckets: dict[int, list[CandleResponse]] = {}
    for candle in sorted_candles:
        ts = int(_as_utc(candle.open_time).timestamp())
        bucket_key = ts - (ts % bucket_seconds)
        buckets.setdefault(bucket_key, []).append(candle)

    aggregated: list[CandleResponse] = []
    for bucket_key in sorted(buckets):
        group = buckets[bucket_key]
        open_time = datetime.fromtimestamp(bucket_key, tz=UTC)
        aggregated.append(
            CandleResponse(
                open_time=open_time,
                open=group[0].open,
                high=str(max(Decimal(candle.high) for candle in group)),
                low=str(min(Decimal(candle.low) for candle in group)),
                close=group[-1].close,
                volume=str(sum(Decimal(candle.volume) for candle in group)),
            )
        )
    return aggregated


def dedupe_candles(candles: list[CandleResponse]) -> list[CandleResponse]:
    """Elimina velas con el mismo instante UTC (datos duplicados del lakehouse)."""
    if not candles:
        return candles
    by_epoch: dict[int, CandleResponse] = {}
    for candle in sorted(candles, key=lambda item: item.open_time):
        epoch = int(_as_utc(candle.open_time).timestamp())
        by_epoch[epoch] = candle
    return [by_epoch[key] for key in sorted(by_epoch)]


def resolve_lakehouse_timeframe(requested: str) -> tuple[str, int | None]:
    """
    Devuelve (timeframe_lakehouse, bucket_minutes|None).
    Marcos 10m/15m se agregan desde 1m en la API.
    """
    mapping: dict[str, tuple[str, int | None]] = {
        "1m": ("1m", None),
        "5m": ("5m", None),
        "10m": ("1m", 10),
        "15m": ("1m", 15),
        "1h": ("1h", None),
    }
    if requested not in mapping:
        raise ValueError(f"unsupported timeframe: {requested}")
    return mapping[requested]
