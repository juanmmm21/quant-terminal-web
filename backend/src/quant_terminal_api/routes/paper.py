from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from quant_terminal_api.auth import Principal, require_control
from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_settings
from quant_terminal_api.validation_gate import (
    PromotionStore,
    ValidationReportError,
    evaluate,
    load_report,
)

router = APIRouter(prefix="/paper", tags=["paper"])


class PromoteRequest(BaseModel):
    timeframe: str = Field(min_length=1, max_length=8)
    report_id: str = Field(
        min_length=8,
        max_length=64,
        description="id of the validation report the operator was shown",
    )


def get_promotions(request: Request) -> PromotionStore:
    return cast(PromotionStore, request.app.state.promotions)


@router.get("/promotion")
async def current_promotion(
    store: Annotated[PromotionStore, Depends(get_promotions)],
) -> dict[str, Any]:
    return {"promotion": store.current()}


@router.post("/promote")
async def promote(
    body: PromoteRequest,
    settings: Annotated[TerminalSettings, Depends(get_settings)],
    store: Annotated[PromotionStore, Depends(get_promotions)],
    principal: Annotated[Principal, Depends(require_control)],
) -> dict[str, Any]:
    if body.timeframe not in settings.supported_timeframes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported timeframe: {body.timeframe}")
    try:
        report = load_report(settings.runtime_dir, body.timeframe)
    except ValidationReportError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if report["report_id"] != body.report_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the validation report changed since it was displayed; review the new metrics",
        )
    evaluation = evaluate(report, settings.gate_policy())
    if not evaluation.passed and evaluation.mode == "enforce":
        failed = [check.name for check in evaluation.checks if not check.passed]
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            {"message": "validation gate failed", "failed_checks": failed,
             "gate": evaluation.as_dict()},
        )
    record = store.promote(report, evaluation, promoted_by=principal.label)
    return {"promotion": record, "gate": evaluation.as_dict()}


@router.post("/demote")
async def demote(
    store: Annotated[PromotionStore, Depends(get_promotions)],
    principal: Annotated[Principal, Depends(require_control)],
) -> dict[str, Any]:
    return {"promotion": store.demote(demoted_by=principal.label)}
