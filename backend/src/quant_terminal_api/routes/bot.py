from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from quant_terminal_api.bot_state import BotStateStore
from quant_terminal_api.dependencies import get_bot_state
from quant_terminal_api.models import (
    BotActionResponse,
    BotStatus,
    BotStatusResponse,
    PanicRequest,
)

router = APIRouter(prefix="/bot", tags=["bot"])


@router.get("/status", response_model=BotStatusResponse)
async def get_status(
    store: Annotated[BotStateStore, Depends(get_bot_state)],
) -> BotStatusResponse:
    bot_status, updated_at, message = store.snapshot()
    return BotStatusResponse(status=bot_status, updated_at=updated_at, message=message)


@router.post("/panic", response_model=BotActionResponse)
async def panic(
    body: PanicRequest,
    store: Annotated[BotStateStore, Depends(get_bot_state)],
) -> BotActionResponse:
    if store.status == BotStatus.PANIC:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="bot is already in panic state",
        )
    new_status = store.set_panic(body.reason)
    updated_at = datetime.now(tz=UTC)
    return BotActionResponse(
        status=new_status,
        updated_at=updated_at,
        action="panic",
        message=f"panic activated: {body.reason}",
    )


@router.post("/pause", response_model=BotActionResponse)
async def pause(
    store: Annotated[BotStateStore, Depends(get_bot_state)],
) -> BotActionResponse:
    if store.status == BotStatus.PANIC:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot pause while bot is in panic state",
        )
    new_status = store.set_paused()
    return BotActionResponse(
        status=new_status,
        updated_at=datetime.now(tz=UTC),
        action="pause",
        message="bot paused",
    )


@router.post("/resume", response_model=BotActionResponse)
async def resume(
    store: Annotated[BotStateStore, Depends(get_bot_state)],
) -> BotActionResponse:
    if store.status == BotStatus.PANIC:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot resume while bot is in panic state; manual reset required",
        )
    new_status = store.set_running()
    return BotActionResponse(
        status=new_status,
        updated_at=datetime.now(tz=UTC),
        action="resume",
        message="bot resumed",
    )


@router.post("/reset", response_model=BotActionResponse)
async def reset(
    store: Annotated[BotStateStore, Depends(get_bot_state)],
) -> BotActionResponse:
    previous = store.status
    new_status = store.set_running("reiniciado por operador desde el terminal")
    return BotActionResponse(
        status=new_status,
        updated_at=datetime.now(tz=UTC),
        action="reset",
        message="bot reiniciado" if previous == BotStatus.PANIC else "bot ya estaba en marcha",
    )
