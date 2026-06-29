from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from quant_terminal_api.dependencies import get_audit_reader
from quant_terminal_api.models import AuditEventsResponse
from quant_terminal_api.readers import AuditReader, DataSourceError

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=AuditEventsResponse)
async def list_audit_events(
    reader: Annotated[AuditReader, Depends(get_audit_reader)],
    limit: int = Query(default=50, ge=1, le=500),
    event_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
) -> AuditEventsResponse:
    try:
        events = reader.fetch_events(limit=limit, event_type=event_type, symbol=symbol)
    except DataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AuditEventsResponse(events=events, count=len(events))
