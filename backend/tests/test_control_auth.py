from __future__ import annotations

import json

import pytest
from conftest import ADMIN, ADMIN_TOKEN
from fastapi.testclient import TestClient

from quant_terminal_api.app import create_app
from quant_terminal_api.auth import DeviceRegistry, hash_token
from quant_terminal_api.config import TerminalSettings

CONTROL_ENDPOINTS = [
    ("/api/v1/bot/panic", {"reason": "x"}),
    ("/api/v1/bot/pause", None),
    ("/api/v1/bot/resume", None),
    ("/api/v1/bot/reset", None),
    ("/api/v1/paper/promote", {"timeframe": "1h", "report_id": "0123456789abcdef"}),
    ("/api/v1/paper/demote", None),
]


@pytest.mark.parametrize(("path", "body"), CONTROL_ENDPOINTS)
def test_control_endpoints_reject_missing_and_wrong_tokens(
    client: TestClient, path: str, body: dict[str, str] | None
) -> None:
    assert client.post(path, json=body).status_code == 401
    wrong = {"Authorization": "Bearer not-the-token"}
    assert client.post(path, json=body, headers=wrong).status_code == 401
    basic = {"Authorization": f"Basic {ADMIN_TOKEN}"}
    assert client.post(path, json=body, headers=basic).status_code == 401


@pytest.mark.parametrize(("path", "body"), CONTROL_ENDPOINTS)
def test_control_disabled_without_admin_token(
    settings: TerminalSettings, path: str, body: dict[str, str] | None
) -> None:
    settings.admin_token = None
    client = TestClient(create_app(settings))
    response = client.post(path, json=body, headers=ADMIN)
    assert response.status_code == 503
    assert "TERMINAL_ADMIN_TOKEN" in response.json()["detail"]


def test_read_endpoints_stay_open(client: TestClient) -> None:
    assert client.get("/api/v1/bot/status").status_code == 200
    assert client.get("/api/v1/health").status_code == 200


def test_panic_records_who_pulled_it(client: TestClient) -> None:
    response = client.post("/api/v1/bot/panic", json={"reason": "drill"}, headers=ADMIN)
    assert response.status_code == 200
    status = client.get("/api/v1/bot/status").json()
    assert status["status"] == "panic"
    assert "by operator" in status["message"]


def test_device_registry_stores_only_hashes(settings: TerminalSettings) -> None:
    registry = DeviceRegistry(settings.devices_path)
    token, record = registry.register("iPhone de prueba")
    raw = settings.devices_path.read_text(encoding="utf-8")
    assert token not in raw
    assert hash_token(token) in raw
    assert settings.devices_path.stat().st_mode & 0o077 == 0
    assert registry.authenticate(token) is not None
    assert registry.revoke(record["device_id"])
    assert registry.authenticate(token) is None
    stored = json.loads(raw)
    assert stored[record["device_id"]]["name"] == "iPhone de prueba"
