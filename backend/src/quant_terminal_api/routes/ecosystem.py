from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from quant_terminal_api.config import TerminalSettings
from quant_terminal_api.dependencies import get_settings
from quant_terminal_api.models import EcosystemStatusResponse
from quant_terminal_api.readers.market import lakehouse_is_ready

router = APIRouter(tags=["ecosystem"])


def _load_manifest(runtime_dir: Path) -> dict[str, Any] | None:
    manifest_path = runtime_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


@router.get("/ecosystem/status", response_model=EcosystemStatusResponse)
async def ecosystem_status(
    settings: Annotated[TerminalSettings, Depends(get_settings)],
) -> EcosystemStatusResponse:
    ticks_path = settings.ticks_jsonl_path
    ticks_ready = ticks_path.exists() and ticks_path.stat().st_size > 0
    return EcosystemStatusResponse(
        data_mode=settings.data_mode,
        ecosystem_ready=False,
        lakehouse_ready=lakehouse_is_ready(settings.lakehouse_root),
        live_ticks_ready=ticks_ready,
        analysis_ready=settings.analysis_ready,
        paths={
            "lakehouse": str(settings.lakehouse_root),
            "ticks": str(settings.ticks_jsonl_path),
            "runtime": str(settings.runtime_dir),
            "bot_state": str(settings.bot_state_path),
        },
        modules=settings.source_manifest(),
        manifest=_load_manifest(settings.runtime_dir),
        last_checked=datetime.now(tz=UTC),
    )
