"""Async client for OTO's undocumented cloud API.

The protocol was derived from the Apache-2.0 licensed homebridge-oto project.
OTO does not publish or support this API, so every response is validated before
it is exposed to Home Assistant.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

FIREBASE_API_KEY = "AIzaSyBlkDTR_GZSnGJuXdWAtH65ceeXyHtSrIs"
IDENTITY_TOOLKIT = "https://identitytoolkit.googleapis.com/v1"
SECURE_TOKEN = "https://securetoken.googleapis.com/v1"
EMS = "https://oto-cloud-service-ems-prod-716180884817.us-central1.run.app"
SCHEDULER = "https://oto-cloud-service-scheduler-prod-716180884817.us-central1.run.app"

REQUEST_TIMEOUT = 20


class OtoError(Exception):
    """Base OTO exception."""


class OtoAuthError(OtoError):
    """Authentication or authorization failed."""


class OtoConnectionError(OtoError):
    """OTO cloud could not be reached."""


class OtoResponseError(OtoError):
    """OTO returned an invalid or unsuccessful response."""


@dataclass(slots=True)
class OtoCredentials:
    """Refreshable OTO credentials."""

    uid: str
    refresh_token: str
    id_token: str | None = None
    expires_at: float = 0


@dataclass(frozen=True, slots=True)
class OtoZone:
    """An OTO watering zone."""

    id: str
    name: str
    watering_time_min: float | None = None


@dataclass(frozen=True, slots=True)
class OtoDevice:
    """An OTO controller."""

    id: str
    name: str
    zones: tuple[OtoZone, ...] = ()
    watering: bool = False
    schedule_id: str | None = None
    firmware_version: str | None = None


@dataclass(frozen=True, slots=True)
class ManualStartResult:
    """Result returned by OTO for a manual watering request."""

    schedule_id: str | None
    runtime_min: float | None


TokenUpdateCallback = Callable[[OtoCredentials], Awaitable[None] | None]


class OtoApiClient:
    """Minimal asynchronous client for the OTO cloud."""

    def __init__(
        self,
        session: ClientSession,
        credentials: OtoCredentials | None = None,
        token_update_callback: TokenUpdateCallback | None = None,
    ) -> None:
        self._session = session
        self.credentials = credentials
        self._token_update_callback = token_update_callback
        self._refresh_lock = asyncio.Lock()

    async def async_login(self, email: str, password: str) -> OtoCredentials:
        """Authenticate with Firebase using an email and password."""
        payload = await self._request_json(
            "POST",
            f"{IDENTITY_TOOLKIT}/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
            json={"email": email, "password": password, "returnSecureToken": True},
            auth_request=True,
        )
        try:
            credentials = OtoCredentials(
                uid=str(payload["localId"]),
                refresh_token=str(payload["refreshToken"]),
                id_token=str(payload["idToken"]),
                expires_at=time.time() + int(payload.get("expiresIn", 3600)),
            )
        except (KeyError, TypeError, ValueError) as err:
            raise OtoResponseError("OTO sign-in returned an invalid response") from err
        self.credentials = credentials
        await self._notify_token_update()
        return credentials

    async def async_refresh_token(self) -> None:
        """Refresh the Firebase ID token without retaining the account password."""
        async with self._refresh_lock:
            if self.credentials is None or not self.credentials.refresh_token:
                raise OtoAuthError("OTO credentials are missing")
            if self.credentials.id_token and time.time() < self.credentials.expires_at - 60:
                return
            payload = await self._request_json(
                "POST",
                f"{SECURE_TOKEN}/token?key={FIREBASE_API_KEY}",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.credentials.refresh_token,
                },
                auth_request=True,
            )
            try:
                self.credentials.uid = str(payload["user_id"])
                self.credentials.refresh_token = str(payload["refresh_token"])
                self.credentials.id_token = str(payload["id_token"])
                self.credentials.expires_at = time.time() + int(payload.get("expires_in", 3600))
            except (KeyError, TypeError, ValueError) as err:
                raise OtoResponseError("OTO token refresh returned an invalid response") from err
            await self._notify_token_update()

    async def async_get_devices(self) -> list[OtoDevice]:
        """Return all devices, zones, and device-level watering state."""
        credentials = await self._async_ensure_token()
        devices_payload = await self._request_json(
            "GET",
            f"{EMS}/account/{credentials.uid}/devices",
            headers=self._auth_headers(credentials),
        )
        if not isinstance(devices_payload, list):
            raise OtoResponseError("OTO devices response was not a list")

        devices: list[OtoDevice] = []
        for raw_device in devices_payload:
            if not isinstance(raw_device, dict) or not raw_device.get("unitName"):
                continue
            device_id = str(raw_device["unitName"])
            zones_payload = await self._request_json(
                "GET",
                f"{EMS}/account/{credentials.uid}/device/{device_id}/zones",
                headers=self._auth_headers(credentials),
            )
            status_payload = await self._request_json(
                "GET",
                f"{EMS}/device/{device_id}/status",
                headers=self._auth_headers(credentials),
            )
            zones: list[OtoZone] = []
            if isinstance(zones_payload, list):
                for raw_zone in zones_payload:
                    if not isinstance(raw_zone, dict) or not raw_zone.get("zoneId"):
                        continue
                    watering_time = raw_zone.get("wateringTime")
                    zones.append(
                        OtoZone(
                            id=str(raw_zone["zoneId"]),
                            name=str(raw_zone.get("zoneName") or raw_zone["zoneId"]),
                            watering_time_min=(
                                float(watering_time)
                                if isinstance(watering_time, (int, float))
                                else None
                            ),
                        )
                    )
            status = status_payload if isinstance(status_payload, dict) else {}
            if "pathIndex" not in status or not (
                status["pathIndex"] is None
                or (isinstance(status["pathIndex"], int) and status["pathIndex"] >= 0)
            ):
                raise OtoResponseError("OTO status response was invalid")
            devices.append(
                OtoDevice(
                    id=device_id,
                    name=str(raw_device.get("userName") or device_id),
                    zones=tuple(zones),
                    watering=status.get("pathIndex") is not None,
                    schedule_id=(str(status["scheduleId"]) if status.get("scheduleId") else None),
                    firmware_version=(str(status["version"]) if status.get("version") else None),
                )
            )
        return devices

    async def async_start_zone(
        self, device_id: str, zone_id: str, watering_depth_mm: float
    ) -> ManualStartResult:
        """Start a zone using a watering depth in millimetres."""
        if not math.isfinite(watering_depth_mm) or not 1.0 <= watering_depth_mm <= 50.0:
            raise ValueError("Watering depth must be between 1 and 50 mm")
        credentials = await self._async_ensure_token()
        payload = await self._request_json(
            "POST",
            f"{SCHEDULER}/manual-start",
            json={
                "uid": credentials.uid,
                "deviceId": device_id,
                "zoneId": zone_id,
                "wateringQuantity": round(float(watering_depth_mm), 2),
            },
            # OTO's current manual-start endpoint does not accept the Firebase
            # token used by EMS. Account identifiers are obtained only from
            # authenticated discovery and are never accepted from user input.
        )
        item = payload.get("schedule_item") if isinstance(payload, dict) else None
        runtime = item.get("runtime_min") if isinstance(item, dict) else None
        return ManualStartResult(
            schedule_id=(
                str(payload["scheduleId"])
                if isinstance(payload, dict) and payload.get("scheduleId")
                else None
            ),
            runtime_min=float(runtime) if isinstance(runtime, (int, float)) else None,
        )

    async def _async_ensure_token(self) -> OtoCredentials:
        credentials = self.credentials
        if credentials is None:
            raise OtoAuthError("OTO credentials are missing")
        if credentials.id_token is None or time.time() > credentials.expires_at - 60:
            await self.async_refresh_token()
        return credentials

    async def _notify_token_update(self) -> None:
        if self._token_update_callback is None or self.credentials is None:
            return
        result = self._token_update_callback(self.credentials)
        if result is not None:
            await result

    @staticmethod
    def _auth_headers(credentials: OtoCredentials) -> dict[str, str]:
        if not credentials.id_token:
            raise OtoAuthError("OTO ID token is missing")
        return {"Authorization": f"Bearer {credentials.id_token}"}

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        auth_request: bool = False,
        allow_non_json: bool = False,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json,
                data=data,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                await self._raise_for_status(response, auth_request=auth_request)
                if allow_non_json:
                    try:
                        return await response.json(content_type=None)
                    except (ValueError, ClientError):
                        return await response.text()
                try:
                    return await response.json(content_type=None)
                except (ValueError, ClientError) as err:
                    raise OtoResponseError("OTO returned malformed JSON") from err
        except OtoError:
            raise
        except (ClientError, TimeoutError) as err:
            raise OtoConnectionError("Unable to reach the OTO cloud") from err

    @staticmethod
    async def _raise_for_status(response: ClientResponse, *, auth_request: bool) -> None:
        if response.status < 400:
            return
        if auth_request or response.status in (401, 403):
            raise OtoAuthError("OTO authentication failed")
        raise OtoResponseError(f"OTO cloud returned HTTP {response.status}")
