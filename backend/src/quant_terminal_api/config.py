from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_samples_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "samples"


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
    bot_state_path: Path = Field(default_factory=lambda: _default_samples_dir() / "bot_state.json")
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    host: str = "127.0.0.1"
    port: int = 8000

    def resolve_paths(self) -> TerminalSettings:
        self.audit_db_path = self.audit_db_path.expanduser().resolve()
        self.metrics_path = self.metrics_path.expanduser().resolve()
        self.equity_path = self.equity_path.expanduser().resolve()
        self.bot_state_path = self.bot_state_path.expanduser().resolve()
        return self
