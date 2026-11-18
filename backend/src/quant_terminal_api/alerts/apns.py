"""Apple Push Notification service client (token-based auth, HTTP/2).

The ``.p8`` signing key is read from a file path given by the operator
(``TERMINAL_APNS_KEY_PATH``); its contents never appear in configuration or logs. A JWT (ES256)
is minted per key and reused for 50 minutes, as Apple recommends (valid up to one hour).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

logger = logging.getLogger(__name__)

HOSTS = {"production": "https://api.push.apple.com", "sandbox": "https://api.sandbox.push.apple.com"}
TOKEN_TTL_SECONDS = 50 * 60


class PushTransport(Protocol):
    def post(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]: ...


class HttpxTransport:
    def __init__(self) -> None:
        import httpx

        self._client = httpx.Client(http2=True, timeout=10.0)

    def post(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        response = self._client.post(url, headers=headers, content=body)
        return response.status_code, response.text


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, slots=True)
class PushResult:
    status: int
    reason: str

    @property
    def device_gone(self) -> bool:
        """The token will never work again: forget it."""
        return self.status == 410 or self.reason in {"BadDeviceToken", "Unregistered"}


class ApnsClient:
    def __init__(
        self,
        *,
        key_path: Path,
        key_id: str,
        team_id: str,
        topic: str,
        transport: PushTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("APNs keys are P-256 (ES256) private keys")
        self._key = key
        self._key_id = key_id
        self._team_id = team_id
        self._topic = topic
        self._transport = transport or HttpxTransport()
        self._clock = clock
        self._token: tuple[str, float] | None = None

    def provider_token(self) -> str:
        now = self._clock()
        if self._token and now - self._token[1] < TOKEN_TTL_SECONDS:
            return self._token[0]
        header = _b64(json.dumps({"alg": "ES256", "kid": self._key_id}).encode())
        claims = _b64(json.dumps({"iss": self._team_id, "iat": int(now)}).encode())
        signing_input = f"{header}.{claims}".encode("ascii")
        der = self._key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        token = f"{header}.{claims}.{signature}"
        self._token = (token, now)
        return token

    def send(
        self, device_token: str, alert: dict[str, Any], *, environment: str = "sandbox",
        critical: bool = False,
    ) -> PushResult:
        payload = {
            "aps": {
                "alert": {"title": alert["title"], "body": alert["body"]},
                "sound": "default",
                "interruption-level": "time-sensitive" if critical else "active",
            },
            "alert_id": alert["alert_id"],
            "kind": alert["kind"],
        }
        headers = {
            "authorization": f"bearer {self.provider_token()}",
            "apns-topic": self._topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }
        url = f"{HOSTS[environment]}/3/device/{device_token}"
        status, body = self._transport.post(url, headers, json.dumps(payload).encode("utf-8"))
        reason = ""
        if body:
            try:
                reason = str(json.loads(body).get("reason", ""))
            except (ValueError, AttributeError):
                reason = body[:100]
        if status != 200:
            logger.warning("apns status=%s reason=%s", status, reason)
        return PushResult(status, reason)
