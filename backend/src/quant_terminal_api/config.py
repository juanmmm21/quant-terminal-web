from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_samples_dir() -> Path:
    return _project_root() / "samples"


def _default_ecosystem_dir() -> Path:
    return _project_root() / "data" / "ecosystem"


def _ecosystem_outputs_present(eco_dir: Path) -> bool:
    required = (
        eco_dir / "metrics.json",
        eco_dir / "equity.json",
        eco_dir / "trades.jsonl",
        eco_dir / "audit.db",
    )
    return all(path.exists() and path.stat().st_size > 0 for path in required)


class TerminalSettings(BaseSettings):
    """Runtime configuration for the terminal API."""

    model_config = SettingsConfigDict(
        env_prefix="TERMINAL_",
        env_file=".env",
        extra="ignore",
    )

    audit_db_path: Path = Field(default_factory=lambda: _default_samples_dir() / "audit.db")
    metrics_path: Path = Field(default_factory=lambda: _default_samples_dir() / "metrics.json")
    equity_path: Path = Field(default_factory=lambda: _default_samples_dir() / "equity.json")
    trades_path: Path = Field(default_factory=lambda: _default_samples_dir() / "trades.jsonl")
    bot_state_path: Path = Field(
        default_factory=lambda: _default_ecosystem_dir() / "bot_state.json"
    )
    lakehouse_root: Path = Field(default_factory=lambda: _project_root() / "data" / "lake")
    lakehouse_duckdb: Path | None = Field(default=None)
    ticks_jsonl_path: Path = Field(
        default_factory=lambda: _project_root() / "data" / "live" / "ticks.jsonl"
    )
    candle_symbol: str = "BTCUSDT"
    candle_timeframe: str = "1h"
    candle_limit: int = 168
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    host: str = "127.0.0.1"
    port: int = 8000

    def resolve_paths(self) -> TerminalSettings:
        self.audit_db_path = self.audit_db_path.expanduser().resolve()
        self.metrics_path = self.metrics_path.expanduser().resolve()
        self.equity_path = self.equity_path.expanduser().resolve()
        self.trades_path = self.trades_path.expanduser().resolve()
        self.bot_state_path = self.bot_state_path.expanduser().resolve()
        self.lakehouse_root = self.lakehouse_root.expanduser().resolve()
        self.ticks_jsonl_path = self.ticks_jsonl_path.expanduser().resolve()
        if self.lakehouse_duckdb is not None:
            self.lakehouse_duckdb = self.lakehouse_duckdb.expanduser().resolve()

        eco_dir = _default_ecosystem_dir().resolve()
        samples = _default_samples_dir().resolve()
        if _ecosystem_outputs_present(eco_dir):
            if self.audit_db_path == (samples / "audit.db").resolve():
                self.audit_db_path = eco_dir / "audit.db"
            if self.metrics_path == (samples / "metrics.json").resolve():
                self.metrics_path = eco_dir / "metrics.json"
            if self.equity_path == (samples / "equity.json").resolve():
                self.equity_path = eco_dir / "equity.json"
            if self.trades_path == (samples / "trades.jsonl").resolve():
                self.trades_path = eco_dir / "trades.jsonl"
            default_bot = (_default_ecosystem_dir() / "bot_state.json").resolve()
            if self.bot_state_path == default_bot:
                self.bot_state_path = eco_dir / "bot_state.json"
        return self

    @property
    def ecosystem_ready(self) -> bool:
        eco_dir = _default_ecosystem_dir().resolve()
        try:
            using_ecosystem = self.metrics_path.resolve().parent == eco_dir
        except OSError:
            return False
        return using_ecosystem and _ecosystem_outputs_present(eco_dir)

    @property
    def data_mode(self) -> str:
        from quant_terminal_api.readers.market import lakehouse_is_ready

        if self.ecosystem_ready:
            return "ecosystem"
        if lakehouse_is_ready(self.lakehouse_root):
            return "live"
        return "demo"

    def source_manifest(self) -> dict[str, str]:
        """Mapa de fuentes activas para /ecosystem/status."""
        eco_dir = _default_ecosystem_dir().resolve()
        using_ecosystem = _ecosystem_outputs_present(eco_dir)
        return {
            "audit": "trade-audit-logger" if using_ecosystem else "samples",
            "metrics": "quant-metrics-calculator" if using_ecosystem else "samples",
            "equity": "order-routing-gateway+metrics" if using_ecosystem else "samples",
            "trades": "order-routing-gateway" if using_ecosystem else "samples",
            "candles": "market-data-lakehouse",
            "ticks": "websocket-feed-handler",
            "signals": "alpha-signal-generator" if using_ecosystem else "none",
            "risk": "risk-management-engine" if using_ecosystem else "none",
        }
