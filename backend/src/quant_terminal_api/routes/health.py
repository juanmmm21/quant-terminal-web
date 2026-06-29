from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from quant_terminal_api import __version__
from quant_terminal_api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        timestamp=datetime.now(tz=UTC),
    )
