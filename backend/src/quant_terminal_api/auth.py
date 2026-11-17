"""Authentication for control endpoints (kill switch, pause, promotion, devices).

Two kinds of bearer tokens are accepted:

* the operator token, read only from the ``TERMINAL_ADMIN_TOKEN`` environment variable;
* per-device tokens (the iOS app), created by the operator. Only their SHA-256 is stored, so
  the registry file never holds a usable secret; each one can be revoked on its own.

If no operator token is configured, every control endpoint answers 503: control is disabled
rather than open.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
TOKEN_PREFIX = "qtd_"


@dataclass(frozen=True, slots=True)
class Principal:
    kind: str  # "operator" | "device"
    subject: str  # "operator" or the device id

    @property
    def label(self) -> str:
        return self.subject if self.kind == "operator" else f"device:{self.subject}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DeviceRegistry:
    """Device tokens (hashed) and their APNs push tokens, persisted to JSON."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("device registry unreadable, treating as empty: %s", exc)
            return {}
        return cast(dict[str, dict[str, Any]], raw) if isinstance(raw, dict) else {}

    def _write(self, devices: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(devices, indent=2) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self._path)

    def register(self, name: str) -> tuple[str, dict[str, Any]]:
        """Create a device; returns the plaintext token (shown once) and its public record."""
        device_id = secrets.token_hex(8)
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        record: dict[str, Any] = {
            "device_id": device_id,
            "name": name,
            "token_sha256": hash_token(token),
            "created_at": datetime.now(tz=UTC).isoformat(),
            "revoked_at": None,
            "last_seen_at": None,
            "apns_token": None,
            "apns_environment": None,
        }
        with self._lock:
            devices = self._read()
            devices[device_id] = record
            self._write(devices)
        return token, self.public(record)

    def authenticate(self, token: str) -> dict[str, Any] | None:
        digest = hash_token(token)
        with self._lock:
            devices = self._read()
            for record in devices.values():
                stored = str(record.get("token_sha256", ""))
                if hmac.compare_digest(stored, digest) and not record.get("revoked_at"):
                    record["last_seen_at"] = datetime.now(tz=UTC).isoformat()
                    self._write(devices)
                    return record
        return None

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            devices = self._read()
            record = devices.get(device_id)
            if record is None:
                return False
            record["revoked_at"] = datetime.now(tz=UTC).isoformat()
            record["apns_token"] = None
            self._write(devices)
            return True

    def set_push_token(self, device_id: str, apns_token: str, environment: str) -> None:
        with self._lock:
            devices = self._read()
            if device_id not in devices:
                raise KeyError(device_id)
            devices[device_id]["apns_token"] = apns_token
            devices[device_id]["apns_environment"] = environment
            self._write(devices)

    def list_public(self) -> list[dict[str, Any]]:
        return [self.public(record) for record in self._read().values()]

    def push_targets(self) -> list[tuple[str, str, str]]:
        """(device_id, apns_token, environment) for every active device with a push token."""
        return [
            (str(r["device_id"]), str(r["apns_token"]), str(r.get("apns_environment") or "sandbox"))
            for r in self._read().values()
            if r.get("apns_token") and not r.get("revoked_at")
        ]

    @staticmethod
    def public(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "device_id": record["device_id"],
            "name": record["name"],
            "created_at": record["created_at"],
            "revoked_at": record.get("revoked_at"),
            "last_seen_at": record.get("last_seen_at"),
            "push_enabled": bool(record.get("apns_token")),
        }


def _admin_token(request: Request) -> str | None:
    secret = request.app.state.settings.admin_token
    if secret is None:
        return None
    value = str(secret.get_secret_value())
    return value or None


def get_device_registry(request: Request) -> DeviceRegistry:
    return cast(DeviceRegistry, request.app.state.devices)


def require_control(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """Operator or device token. Used by the kill switch and the other bot controls."""
    admin = _admin_token(request)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="control API disabled: set TERMINAL_ADMIN_TOKEN to enable it",
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    if hmac.compare_digest(token.encode("utf-8"), admin.encode("utf-8")):
        return Principal("operator", "operator")
    record = get_device_registry(request).authenticate(token)
    if record is not None:
        return Principal("device", str(record["device_id"]))
    logger.warning("rejected control request from %s", request.client)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_operator(principal: Annotated[Principal, Depends(require_control)]) -> Principal:
    """Operator only: device management cannot be done with a device token."""
    if principal.kind != "operator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="operator token required")
    return principal
