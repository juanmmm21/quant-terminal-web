from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conftest import ADMIN
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi.testclient import TestClient

from quant_terminal_api.alerts.apns import ApnsClient
from quant_terminal_api.alerts.dispatcher import AlertDispatcher
from quant_terminal_api.app import create_app
from quant_terminal_api.auth import DeviceRegistry
from quant_terminal_api.config import TerminalSettings

PUSH_TOKEN = "ab" * 32


def _client(settings: TerminalSettings, tmp_path: Path) -> TestClient:
    settings.paper_dir = tmp_path / "paper"
    settings.paper_dir.mkdir()
    return TestClient(create_app(settings))


def _device(client: TestClient) -> tuple[str, dict[str, str]]:
    created = client.post("/api/v1/devices", json={"name": "iPhone"}, headers=ADMIN)
    assert created.status_code == 201
    body = created.json()
    return body["device"]["device_id"], {"Authorization": f"Bearer {body['token']}"}


def test_device_tokens_have_device_scope(settings: TerminalSettings, tmp_path: Path) -> None:
    client = _client(settings, tmp_path)
    device_id, device = _device(client)
    # a device can read the overview and pull the kill switch...
    assert client.get("/api/v1/mobile/overview", headers=device).status_code == 200
    panic = client.post("/api/v1/bot/panic", json={"reason": "from phone"}, headers=device)
    assert panic.status_code == 200
    assert f"device:{device_id}" in client.get("/api/v1/bot/status").json()["message"]
    # ...but cannot manage devices
    assert client.post("/api/v1/devices", json={"name": "x"}, headers=device).status_code == 403
    assert client.get("/api/v1/devices", headers=device).status_code == 403
    # and once revoked it is useless
    assert client.delete(f"/api/v1/devices/{device_id}", headers=ADMIN).status_code == 200
    assert client.get("/api/v1/mobile/overview", headers=device).status_code == 401
    assert client.get("/api/v1/mobile/overview").status_code == 401


def test_push_token_registration(settings: TerminalSettings, tmp_path: Path) -> None:
    client = _client(settings, tmp_path)
    device_id, device = _device(client)
    bad = client.put("/api/v1/devices/me/push-token", json={"apns_token": "nothex"},
                     headers=device)
    assert bad.status_code == 422
    assert client.put("/api/v1/devices/me/push-token", json={"apns_token": PUSH_TOKEN},
                      headers=ADMIN).status_code == 403
    ok = client.put("/api/v1/devices/me/push-token",
                    json={"apns_token": PUSH_TOKEN.upper(), "environment": "sandbox"},
                    headers=device)
    assert ok.status_code == 200
    listed = client.get("/api/v1/devices", headers=ADMIN).json()["devices"]
    assert listed[0]["push_enabled"] is True and "token_sha256" not in listed[0]
    assert DeviceRegistry(settings.devices_path).push_targets() == [
        (device_id, PUSH_TOKEN, "sandbox")
    ]


def test_overview_reports_bots_pnl_and_alerts(settings: TerminalSettings, tmp_path: Path) -> None:
    client = _client(settings, tmp_path)
    paper = settings.paper_dir
    (paper / "state.json").write_text(json.dumps({"initial_cash": "10000", "position": "0.001"}),
                                      encoding="utf-8")
    (paper / "equity.jsonl").write_text(
        json.dumps({"at": "2026-11-18T00:00:00+00:00", "equity": "10012.5", "price": "65000"})
        + "\n", encoding="utf-8")
    (paper / "heartbeat.json").write_text(json.dumps(
        {"at": datetime.now(tz=UTC).isoformat(), "venue": "binance-testnet", "action": "hold"}),
        encoding="utf-8")
    (paper / "events.jsonl").write_text(
        json.dumps({"at": "2026-11-18T00:01:00+00:00", "kind": "killed", "cancelled": 2}) + "\n",
        encoding="utf-8")
    (paper / "fills.jsonl").write_text(json.dumps({
        "filled_at": "2026-11-18T00:00:30+00:00", "side": "buy", "quantity": "0.001",
        "price": "65000", "venue": "binance-testnet"}) + "\n", encoding="utf-8")
    body = client.get("/api/v1/mobile/overview", headers=ADMIN).json()
    assert body["trader"]["alive"] is True and body["trader"]["venue"] == "binance-testnet"
    assert body["pnl"]["pnl"] == "12.5" and body["pnl"]["position"] == "0.001"
    assert [a["kind"] for a in body["alerts"]] == ["killed", "fill"]
    assert body["alerts"][0]["severity"] == "critical"
    assert body["strategy"] is None


def _key(tmp_path: Path) -> tuple[Path, ec.EllipticCurvePublicKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "AuthKey_TEST.p8"
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    return path, key.public_key()


def _b64d(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class FakePush:
    def __init__(self, statuses: list[tuple[int, str]]) -> None:
        self.statuses = statuses
        self.sent: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def post(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        self.sent.append((url, headers, json.loads(body)))
        return self.statuses.pop(0)


def test_apns_provider_token_is_a_valid_es256_jwt(tmp_path: Path) -> None:
    path, public = _key(tmp_path)
    clock = [1_700_000_000.0]
    client = ApnsClient(key_path=path, key_id="KEY123", team_id="TEAM456", topic="app.quant",
                        transport=FakePush([]), clock=lambda: clock[0])
    token = client.provider_token()
    header, claims, signature = token.split(".")
    assert json.loads(_b64d(header)) == {"alg": "ES256", "kid": "KEY123"}
    assert json.loads(_b64d(claims)) == {"iss": "TEAM456", "iat": 1_700_000_000}
    raw = _b64d(signature)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    public.verify(der, f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))  # no raise
    assert client.provider_token() == token  # cached
    clock[0] += 51 * 60
    assert client.provider_token() != token  # refreshed before Apple's one-hour limit


def test_dispatcher_pushes_new_alerts_once_and_forgets_dead_tokens(
    settings: TerminalSettings, tmp_path: Path
) -> None:
    path, _ = _key(tmp_path)
    paper = tmp_path / "paper"
    paper.mkdir()
    registry = DeviceRegistry(settings.devices_path)
    _, alive = registry.register("alive")
    gone_token, gone = registry.register("gone")
    registry.set_push_token(alive["device_id"], "aa" * 32, "sandbox")
    registry.set_push_token(gone["device_id"], "bb" * 32, "production")
    transport = FakePush([(200, ""), (410, '{"reason":"Unregistered"}')])
    client = ApnsClient(key_path=path, key_id="K", team_id="T", topic="app.quant",
                        transport=transport)
    dispatcher = AlertDispatcher(paper, registry, client)
    with (paper / "events.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": "t1", "kind": "kill_retry"}) + "\n")
        handle.write(json.dumps({"at": "t2", "kind": "reconciled"}) + "\n")  # info: not pushed
    [(alert, reached)] = dispatcher.poll()
    assert alert.kind == "kill_retry" and reached == 1
    hosts = sorted(url.split("/3/")[0] for url, _, _ in transport.sent)
    assert hosts == ["https://api.push.apple.com", "https://api.sandbox.push.apple.com"]
    assert transport.sent[0][2]["aps"]["interruption-level"] == "time-sensitive"
    assert registry.push_targets() == [(alive["device_id"], "aa" * 32, "sandbox")]
    assert AlertDispatcher(paper, registry, client).poll() == []  # offsets survive a restart
    assert gone_token not in settings.devices_path.read_text(encoding="utf-8")
