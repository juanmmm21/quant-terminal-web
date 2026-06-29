from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quant_terminal_api.models import (
    AnalysisSnapshotResponse,
    IndicatorSnapshotResponse,
    RecommendationResponse,
    SignalMarkerResponse,
    TrainingStatsResponse,
)

logger = logging.getLogger(__name__)


class AnalysisCacheError(Exception):
    """Raised when analysis cache cannot be read."""


def _utc_from_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class AnalysisCacheReader:
    """Lee snapshots de análisis generados por scripts/analysis_engine.py."""

    def __init__(self, runtime_dir: Path, *, symbol: str) -> None:
        self._runtime_dir = runtime_dir
        self._symbol = symbol

    def _cache_path(self, timeframe: str) -> Path:
        return self._runtime_dir / f"analysis_{timeframe}.json"

    def is_ready(self, timeframe: str) -> bool:
        path = self._cache_path(timeframe)
        return path.exists() and path.stat().st_size > 0

    def load_raw(self, timeframe: str) -> dict[str, Any]:
        path = self._cache_path(timeframe)
        if not path.exists():
            raise AnalysisCacheError(
                f"analysis cache missing for {timeframe}. "
                "Run: python3 scripts/start_terminal.py"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AnalysisCacheError(f"failed to read analysis cache: {exc}") from exc
        if not isinstance(payload, dict):
            raise AnalysisCacheError("analysis cache must be a JSON object")
        return payload

    def load_snapshot(self, timeframe: str) -> AnalysisSnapshotResponse:
        raw = self.load_raw(timeframe)
        recommendation_raw = raw.get("recommendation", {})
        indicators_raw = raw.get("indicators", {})
        training_raw = raw.get("training", {})
        signals_raw = raw.get("signals", [])

        if not isinstance(recommendation_raw, dict):
            recommendation_raw = {}
        if not isinstance(indicators_raw, dict):
            indicators_raw = {}
        if not isinstance(training_raw, dict):
            training_raw = {}
        if not isinstance(signals_raw, list):
            signals_raw = []

        updated_at_raw = raw.get("updated_at")
        updated_at = (
            _utc_from_iso8601(updated_at_raw)
            if isinstance(updated_at_raw, str)
            else datetime.now(tz=UTC)
        )

        recommendation = RecommendationResponse(
            verdict=str(recommendation_raw.get("verdict", "hold")),
            action=str(recommendation_raw.get("action", "hold")),
            side=recommendation_raw.get("side"),
            confidence=float(recommendation_raw.get("confidence", 0.0)),
            reason=str(recommendation_raw.get("reason", "sin señal clara")),
            strategy_id=str(recommendation_raw.get("strategy_id", "unknown")),
            reference_price=str(recommendation_raw.get("reference_price", "0")),
            event_time=(
                _utc_from_iso8601(str(recommendation_raw["event_time"]))
                if recommendation_raw.get("event_time")
                else None
            ),
        )

        indicators = IndicatorSnapshotResponse(
            rsi=_optional_float(indicators_raw.get("rsi")),
            macd_line=_optional_float(indicators_raw.get("macd_line")),
            signal_line=_optional_float(indicators_raw.get("signal_line")),
            sma_20=_optional_float(indicators_raw.get("sma_20")),
            ema_20=_optional_float(indicators_raw.get("ema_20")),
        )

        training = TrainingStatsResponse(
            timeframe=timeframe,
            symbol=str(training_raw.get("symbol", self._symbol)),
            bars_analyzed=int(training_raw.get("bars_analyzed", 0)),
            signal_count=int(training_raw.get("signal_count", 0)),
            enter_signals=int(training_raw.get("enter_signals", 0)),
            exit_signals=int(training_raw.get("exit_signals", 0)),
            directional_win_rate=str(training_raw.get("directional_win_rate", "0")),
            selected_strategy=str(training_raw.get("selected_strategy", "unknown")),
            trained_at=(
                _utc_from_iso8601(str(training_raw["trained_at"]))
                if training_raw.get("trained_at")
                else updated_at
            ),
        )

        markers: list[SignalMarkerResponse] = []
        for item in signals_raw:
            if not isinstance(item, dict):
                continue
            event_time = item.get("event_time")
            if not isinstance(event_time, str):
                continue
            markers.append(
                SignalMarkerResponse(
                    event_time=_utc_from_iso8601(event_time),
                    action=str(item.get("action", "hold")),
                    side=item.get("side"),
                    confidence=float(item.get("confidence", 0.0)),
                    reason=str(item.get("reason", "")),
                    reference_price=str(item.get("reference_price", "0")),
                    strategy_id=str(item.get("strategy_id", "")),
                )
            )

        return AnalysisSnapshotResponse(
            symbol=str(raw.get("symbol", self._symbol)),
            timeframe=timeframe,
            last_price=str(raw.get("last_price", "0")),
            currency=str(raw.get("currency", "USDT")),
            updated_at=updated_at,
            recommendation=recommendation,
            indicators=indicators,
            training=training,
            signals=markers,
        )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return None
    return None
