from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_samples_dir() -> Path:
    return _project_root() / "samples"


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
    bot_state_path: Path = Field(default_factory=lambda: _default_samples_dir() / "bot_state.json")
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
        return self

    @property
    def data_mode(self) -> str:
        from quant_terminal_api.readers.market import lakehouse_is_ready

        return "live" if lakehouse_is_ready(self.lakehouse_root) else "demo"
