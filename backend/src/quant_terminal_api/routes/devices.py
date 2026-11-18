"""Per-device tokens for the iOS app (created and revoked by the operator only)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from quant_terminal_api.auth import (
    DeviceRegistry,
    Principal,
    get_device_registry,
    require_control,
    require_operator,
)

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PushTokenUpdate(BaseModel):
    apns_token: str = Field(pattern=r"^[0-9a-fA-F]{64,200}$")
    environment: str = Field(default="sandbox", pattern=r"^(sandbox|production)$")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceCreate,
    registry: Annotated[DeviceRegistry, Depends(get_device_registry)],
    _operator: Annotated[Principal, Depends(require_operator)],
) -> dict[str, Any]:
    token, device = registry.register(body.name)
    return {
        "device": device,
        "token": token,
        "note": "shown once: paste it into the app now; only its SHA-256 is stored",
    }


@router.get("")
async def list_devices(
    registry: Annotated[DeviceRegistry, Depends(get_device_registry)],
    _operator: Annotated[Principal, Depends(require_operator)],
) -> dict[str, Any]:
    return {"devices": registry.list_public()}


@router.delete("/{device_id}")
async def revoke_device(
    device_id: str,
    registry: Annotated[DeviceRegistry, Depends(get_device_registry)],
    _operator: Annotated[Principal, Depends(require_operator)],
) -> dict[str, Any]:
    if not registry.revoke(device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown device")
    return {"revoked": device_id}


@router.put("/me/push-token")
async def set_push_token(
    body: PushTokenUpdate,
    registry: Annotated[DeviceRegistry, Depends(get_device_registry)],
    principal: Annotated[Principal, Depends(require_control)],
) -> dict[str, Any]:
    if principal.kind != "device":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only a device can register its token")
    registry.set_push_token(principal.subject, body.apns_token.lower(), body.environment)
    return {"device_id": principal.subject, "push_enabled": True}
