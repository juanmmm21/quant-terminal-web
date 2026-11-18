"""Turn journal records into user-facing alerts (Spanish copy, shown in the iOS app)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True, slots=True)
class Alert:
    alert_id: str
    at: str
    kind: str
    severity: str  # info | warning | critical
    title: str
    body: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _alert_id(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]


def from_event(record: dict[str, Any]) -> Alert | None:
    kind = str(record.get("kind", ""))
    at = str(record.get("at", ""))
    mapping: dict[str, tuple[str, str, str]] = {
        "killed": ("critical", "Parada de emergencia aplicada",
                   f"Órdenes canceladas: {record.get('cancelled', 0)}."),
        "kill_retry": ("critical", "Parada de emergencia pendiente",
                       "El exchange no responde; se reintenta cancelar cada ciclo."),
        "unknown_outcome": ("warning", "Orden en estado desconocido",
                            "Se conciliará con el exchange antes de enviar nada más."),
        "risk_rejected": ("warning", "Orden bloqueada por riesgo", str(record.get("reason", ""))),
        "halt": ("warning", "Trading detenido", str(record.get("reason", ""))),
        "reconcile_failed": ("warning", "No se pudo conciliar",
                             "El exchange no responde a la consulta de órdenes."),
    }
    if kind not in mapping:
        return None
    severity, title, body = mapping[kind]
    return Alert(_alert_id(record), at, kind, severity, title, body)


def from_fill(record: dict[str, Any]) -> Alert:
    side = "Compra" if record.get("side") == "buy" else "Venta"
    return Alert(
        _alert_id(record),
        str(record.get("filled_at", "")),
        "fill",
        "info",
        f"{side} ejecutada (paper)",
        f"{record.get('quantity')} a {record.get('price')} en {record.get('venue')}",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def recent_alerts(paper_dir: Path, limit: int = 50) -> list[Alert]:
    alerts = [a for a in (from_event(r) for r in read_jsonl(paper_dir / "events.jsonl")) if a]
    alerts += [from_fill(r) for r in read_jsonl(paper_dir / "fills.jsonl")]
    alerts.sort(key=lambda a: a.at, reverse=True)
    return alerts[:limit]
