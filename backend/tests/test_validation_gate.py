from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient

from quant_terminal_api.validation_gate import GatePolicy, evaluate


def _report(**overrides: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "version": 1,
        "report_id": "abcdef0123456789",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "strategy": "rsi_mean_reversion",
        "n_trials": 10,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "deflated_sharpe_ratio": 0.97,
        "probabilistic_sharpe_ratio": 0.99,
        "pbo": 0.2,
        "pbo_error": None,
        "walk_forward": {"oos_sharpe_annualized": 1.1},
        "purged_kfold": {"oos_sharpe_annualized": 0.9},
        "period_start": "2024-11-18T00:00:00+00:00",
        "period_end": "2026-11-17T00:00:00+00:00",
    }
    report.update(overrides)
    return report


def _write(runtime: Path, report: dict[str, Any]) -> None:
    (runtime / f"validation_{report['timeframe']}.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


def test_gate_passes_a_robust_report() -> None:
    assert evaluate(_report(), GatePolicy()).passed


@pytest.mark.parametrize(
    ("override", "failing"),
    [
        ({"deflated_sharpe_ratio": 0.4}, "deflated_sharpe_ratio"),
        ({"pbo": 0.8}, "pbo"),
        ({"pbo": None, "pbo_error": "PBO needs at least two strategies"}, "pbo"),
        ({"walk_forward": {"oos_sharpe_annualized": -0.3}}, "walk_forward_oos_sharpe"),
        ({"purged_kfold": {"oos_sharpe_annualized": 0.0}}, "purged_kfold_oos_sharpe"),
        (
            {"generated_at": (datetime.now(tz=UTC) - timedelta(days=3)).isoformat()},
            "report_age_hours",
        ),
    ],
)
def test_gate_fails_each_check(override: dict[str, Any], failing: str) -> None:
    evaluation = evaluate(_report(**override), GatePolicy())
    assert not evaluation.passed
    assert [check.name for check in evaluation.checks if not check.passed] == [failing]


def test_validation_endpoint_shows_metrics_and_gate(client: TestClient, settings: Any) -> None:
    assert client.get("/api/v1/validation?timeframe=1h").status_code == 404
    _write(settings.runtime_dir, _report())
    body = client.get("/api/v1/validation?timeframe=1h").json()
    assert body["report"]["deflated_sharpe_ratio"] == 0.97
    assert body["gate"]["passed"] is True
    assert {check["name"] for check in body["gate"]["checks"]} >= {"pbo", "deflated_sharpe_ratio"}


def test_promotion_requires_the_displayed_report(client: TestClient, settings: Any) -> None:
    _write(settings.runtime_dir, _report())
    stale = client.post(
        "/api/v1/paper/promote", json={"timeframe": "1h", "report_id": "0000000000000000"},
        headers=ADMIN,
    )
    assert stale.status_code == 409
    ok = client.post(
        "/api/v1/paper/promote", json={"timeframe": "1h", "report_id": "abcdef0123456789"},
        headers=ADMIN,
    )
    assert ok.status_code == 200
    promotion = client.get("/api/v1/paper/promotion").json()["promotion"]
    assert promotion["strategy"] == "rsi_mean_reversion"
    assert promotion["gate_passed"] is True
    assert promotion["validation"]["pbo"] == 0.2
    demoted = client.post("/api/v1/paper/demote", headers=ADMIN)
    assert demoted.json()["promotion"]["active"] is False
    assert client.get("/api/v1/paper/promotion").json()["promotion"] is None


def test_enforce_mode_blocks_a_failing_strategy(client: TestClient, settings: Any) -> None:
    _write(settings.runtime_dir, _report(deflated_sharpe_ratio=0.0001, pbo=0.9))
    response = client.post(
        "/api/v1/paper/promote", json={"timeframe": "1h", "report_id": "abcdef0123456789"},
        headers=ADMIN,
    )
    assert response.status_code == 412
    assert set(response.json()["detail"]["failed_checks"]) == {"deflated_sharpe_ratio", "pbo"}
    assert client.get("/api/v1/paper/promotion").json()["promotion"] is None


def test_acknowledge_mode_promotes_but_flags_it(settings: Any) -> None:
    from quant_terminal_api.app import create_app

    settings.paper_gate_mode = "acknowledge"
    client = TestClient(create_app(settings))
    _write(settings.runtime_dir, _report(deflated_sharpe_ratio=0.0001))
    response = client.post(
        "/api/v1/paper/promote", json={"timeframe": "1h", "report_id": "abcdef0123456789"},
        headers=ADMIN,
    )
    assert response.status_code == 200
    assert response.json()["promotion"]["gate_passed"] is False
