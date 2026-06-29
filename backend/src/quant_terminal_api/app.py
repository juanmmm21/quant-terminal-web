from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from quant_terminal_api import __version__
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_settings
from quant_terminal_api.routes import audit, bot, health, metrics

logger = logging.getLogger(__name__)


def create_app(settings: TerminalSettings | None = None) -> FastAPI:
    resolved = (settings or TerminalSettings()).resolve_paths()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "quant-terminal-api v%s starting (audit=%s, metrics=%s, equity=%s)",
            __version__,
            resolved.audit_db_path,
            resolved.metrics_path,
            resolved.equity_path,
        )
        yield
        get_settings.cache_clear()
        logger.info("quant-terminal-api shutdown complete")

    app = FastAPI(
        title="quant-terminal-api",
        version=__version__,
        description="REST API for quant-terminal-web and quant-terminal-ios",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = resolved.api_prefix.rstrip("/")
    app.include_router(health.router, prefix=prefix)
    app.include_router(bot.router, prefix=prefix)
    app.include_router(metrics.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)
    return app
