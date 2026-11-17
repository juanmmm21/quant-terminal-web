"""Promotion gate: no strategy reaches paper trading without its overfitting metrics.

The validation report (``data/runtime/validation_{tf}.json``) is written by
``scripts/strategy_validation.py``. Promotion requires that the client sends the ``report_id``
it displayed, so the operator has seen the exact deflated Sharpe, PBO and out-of-sample results
being acted on. In ``enforce`` mode (default) a report that fails any threshold blocks promotion;
in ``acknowledge`` mode it can be promoted but stays flagged as ``gate_passed: false``
everywhere, including the public view.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class ValidationReportError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GatePolicy:
    min_deflated_sharpe: float = 0.95
    max_pbo: float = 0.5
    min_oos_sharpe: float = 0.0
    max_report_age_hours: float = 24.0
    mode: str = "enforce"  # "enforce" | "acknowledge"


@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    value: float | None
    threshold: float
    comparison: str  # ">=" | "<=" | ">"
    passed: bool
    explanation: str


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    passed: bool
    mode: str
    checks: tuple[GateCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "mode": self.mode,
            "checks": [asdict(check) for check in self.checks],
        }


def load_report(runtime_dir: Path, timeframe: str) -> dict[str, Any]:
    path = runtime_dir / f"validation_{timeframe}.json"
    if not path.exists():
        raise ValidationReportError(
            f"no validation report for {timeframe}; it is written by the analysis engine "
            "(python3 scripts/strategy_validation.py --timeframe " + timeframe + ")"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationReportError(f"unreadable validation report: {exc}") from exc
    if not isinstance(payload, dict) or "report_id" not in payload:
        raise ValidationReportError("validation report is malformed")
    return payload


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def evaluate(
    report: dict[str, Any], policy: GatePolicy, *, now: datetime | None = None
) -> GateEvaluation:
    current = now or datetime.now(tz=UTC)
    dsr = _num(report.get("deflated_sharpe_ratio"))
    pbo = _num(report.get("pbo"))
    wf = _num((report.get("walk_forward") or {}).get("oos_sharpe_annualized"))
    cv = _num((report.get("purged_kfold") or {}).get("oos_sharpe_annualized"))
    try:
        generated = datetime.fromisoformat(str(report.get("generated_at")).replace("Z", "+00:00"))
        age_hours: float | None = (current - generated).total_seconds() / 3600
    except ValueError:
        age_hours = None

    checks = (
        GateCheck(
            "deflated_sharpe_ratio",
            dsr,
            policy.min_deflated_sharpe,
            ">=",
            dsr is not None and dsr >= policy.min_deflated_sharpe,
            f"P[true Sharpe > best of {report.get('n_trials')} zero-skill trials]",
        ),
        GateCheck(
            "pbo",
            pbo,
            policy.max_pbo,
            "<=",
            pbo is not None and pbo <= policy.max_pbo,
            "probability the in-sample winner is below the out-of-sample median"
            + ("" if pbo is not None else f" (not computable: {report.get('pbo_error')})"),
        ),
        GateCheck(
            "walk_forward_oos_sharpe",
            wf,
            policy.min_oos_sharpe,
            ">",
            wf is not None and wf > policy.min_oos_sharpe,
            "annualized Sharpe of the walk-forward out-of-sample picks",
        ),
        GateCheck(
            "purged_kfold_oos_sharpe",
            cv,
            policy.min_oos_sharpe,
            ">",
            cv is not None and cv > policy.min_oos_sharpe,
            "annualized Sharpe of purged k-fold out-of-sample picks (embargoed)",
        ),
        GateCheck(
            "report_age_hours",
            age_hours,
            policy.max_report_age_hours,
            "<=",
            age_hours is not None and age_hours <= policy.max_report_age_hours,
            "the report must be recent",
        ),
    )
    return GateEvaluation(all(check.passed for check in checks), policy.mode, checks)


class PromotionStore:
    """The single strategy currently promoted to paper trading (JSON, atomic writes)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    def current(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) and payload.get("active") else None

    def promote(
        self,
        report: dict[str, Any],
        evaluation: GateEvaluation,
        *,
        promoted_by: str,
    ) -> dict[str, Any]:
        record = {
            "active": True,
            "symbol": report.get("symbol"),
            "timeframe": report.get("timeframe"),
            "strategy": report.get("strategy"),
            "report_id": report.get("report_id"),
            "gate_passed": evaluation.passed,
            "gate_mode": evaluation.mode,
            "promoted_at": datetime.now(tz=UTC).isoformat(),
            "promoted_by": promoted_by,
            "validation": {
                "deflated_sharpe_ratio": report.get("deflated_sharpe_ratio"),
                "pbo": report.get("pbo"),
                "n_trials": report.get("n_trials"),
                "walk_forward_oos_sharpe": (report.get("walk_forward") or {}).get(
                    "oos_sharpe_annualized"
                ),
                "purged_kfold_oos_sharpe": (report.get("purged_kfold") or {}).get(
                    "oos_sharpe_annualized"
                ),
                "period_start": report.get("period_start"),
                "period_end": report.get("period_end"),
            },
        }
        self._write(record)
        logger.warning(
            "strategy %s/%s promoted to paper by %s (gate_passed=%s)",
            record["strategy"],
            record["timeframe"],
            promoted_by,
            evaluation.passed,
        )
        return record

    def demote(self, *, demoted_by: str) -> dict[str, Any] | None:
        current = self.current()
        if current is None:
            return None
        current["active"] = False
        current["demoted_at"] = datetime.now(tz=UTC).isoformat()
        current["demoted_by"] = demoted_by
        self._write(current)
        return current

    def _write(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self._path)

