from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from quant_terminal_api.validation_gate import GatePolicy


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

    audit_db_path: Path = Field(
        default_factory=lambda: _project_root() / "data" / "runtime" / "audit.db"
    )
    metrics_path: Path = Field(default_factory=lambda: _default_samples_dir() / "metrics.json")
    equity_path: Path = Field(default_factory=lambda: _default_samples_dir() / "equity.json")
    trades_path: Path = Field(default_factory=lambda: _default_samples_dir() / "trades.jsonl")
    bot_state_path: Path = Field(
        default_factory=lambda: _project_root() / "data" / "runtime" / "bot_state.json"
    )
    lakehouse_root: Path = Field(default_factory=lambda: _project_root() / "data" / "lake")
    lakehouse_duckdb: Path | None = Field(default=None)
    ticks_jsonl_path: Path = Field(
        default_factory=lambda: _project_root() / "data" / "live" / "ticks.jsonl"
    )
    runtime_dir: Path = Field(default_factory=lambda: _project_root() / "data" / "runtime")
    default_timeframe: str = "1h"
    supported_timeframes: list[str] = Field(
        default_factory=lambda: ["1m", "5m", "10m", "15m", "1h"]
    )
    candle_symbol: str = "BTCUSDT"
    candle_limit: int = 50_000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    host: str = "127.0.0.1"
    port: int = 8000
    # Control endpoints (kill switch, pause, promotion, devices) need this bearer token.
    # Only ever set it through the environment; unset = control API disabled.
    admin_token: SecretStr | None = None
    devices_path: Path = Field(
        default_factory=lambda: _project_root() / "data" / "runtime" / "devices.json"
    )
    promotion_path: Path = Field(
        default_factory=lambda: _project_root() / "data" / "runtime" / "paper_promotion.json"
    )
    gate_min_deflated_sharpe: float = 0.95
    gate_max_pbo: float = 0.5
    gate_min_oos_sharpe: float = 0.0
    gate_max_report_age_hours: float = 24.0
    paper_gate_mode: str = Field(default="enforce", pattern="^(enforce|acknowledge)$")

    def resolve_paths(self) -> TerminalSettings:
        self.audit_db_path = self.audit_db_path.expanduser().resolve()
        self.metrics_path = self.metrics_path.expanduser().resolve()
        self.equity_path = self.equity_path.expanduser().resolve()
        self.trades_path = self.trades_path.expanduser().resolve()
        self.bot_state_path = self.bot_state_path.expanduser().resolve()
        self.lakehouse_root = self.lakehouse_root.expanduser().resolve()
        self.ticks_jsonl_path = self.ticks_jsonl_path.expanduser().resolve()
        self.runtime_dir = self.runtime_dir.expanduser().resolve()
        self.devices_path = self.devices_path.expanduser().resolve()
        self.promotion_path = self.promotion_path.expanduser().resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        if self.lakehouse_duckdb is not None:
            self.lakehouse_duckdb = self.lakehouse_duckdb.expanduser().resolve()

        eco_dir = _default_ecosystem_dir().resolve()
        samples = _default_samples_dir().resolve()
        if _ecosystem_outputs_present(eco_dir):
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

    def gate_policy(self) -> GatePolicy:
        return GatePolicy(
            min_deflated_sharpe=self.gate_min_deflated_sharpe,
            max_pbo=self.gate_max_pbo,
            min_oos_sharpe=self.gate_min_oos_sharpe,
            max_report_age_hours=self.gate_max_report_age_hours,
            mode=self.paper_gate_mode,
        )

    @property
    def analysis_ready(self) -> bool:
        cache = self.runtime_dir / f"analysis_{self.default_timeframe}.json"
        return cache.exists() and cache.stat().st_size > 0

    @property
    def data_mode(self) -> str:
        from quant_terminal_api.readers.market import lakehouse_is_ready

        if lakehouse_is_ready(self.lakehouse_root) and self.analysis_ready:
            return "live"
        if lakehouse_is_ready(self.lakehouse_root):
            return "live"
        return "demo"

    def source_manifest(self) -> dict[str, str]:
        return {
            "candles": "market-data-lakehouse",
            "ticks": "websocket-feed-handler",
            "indicators": "ta-indicators-from-scratch",
            "signals": "alpha-signal-generator",
            "analysis": "quant-terminal-web/runtime",
            "audit": "trade-audit-logger",
        }
