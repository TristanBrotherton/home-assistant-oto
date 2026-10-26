"""Tests for the standalone OTO API client."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

API_PATH = Path(__file__).parents[1] / "custom_components" / "oto" / "api.py"
SPEC = importlib.util.spec_from_file_location("oto_api", API_PATH)
assert SPEC is not None and SPEC.loader is not None
OTO_API = importlib.util.module_from_spec(SPEC)
sys.modules["oto_api"] = OTO_API
SPEC.loader.exec_module(OTO_API)

EMS = OTO_API.EMS
OtoApiClient = OTO_API.OtoApiClient
OtoAuthError = OTO_API.OtoAuthError
OtoCredentials = OTO_API.OtoCredentials
OtoResponseError = OTO_API.OtoResponseError


class FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self.payload = payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def json(self, **kwargs: Any) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    async def text(self) -> str:
        return json.dumps(self.payload)


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_login_exchanges_password_without_retaining_it() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "idToken": "id-token",
                    "refreshToken": "refresh-token",
                    "expiresIn": "3600",
                    "localId": "account-id",
                },
            )
        ]
    )
    client = OtoApiClient(session)  # type: ignore[arg-type]
    credentials = await client.async_login("owner@example.com", "not-retained")

    assert credentials.uid == "account-id"
    assert credentials.refresh_token == "refresh-token"
    assert not hasattr(client, "password")


@pytest.mark.asyncio
async def test_invalid_login_is_auth_error() -> None:
    session = FakeSession([FakeResponse(400, {"error": "INVALID_PASSWORD"})])
    client = OtoApiClient(session)  # type: ignore[arg-type]
    with pytest.raises(OtoAuthError, match="authentication failed"):
        await client.async_login("owner@example.com", "wrong")


@pytest.mark.asyncio
async def test_device_discovery_and_path_index_zero_is_watering() -> None:
    session = FakeSession(
        [
            FakeResponse(200, [{"unitName": "device-1", "userName": "Garden"}]),
            FakeResponse(
                200,
                [{"zoneId": "zone-1", "zoneName": "Lawn", "wateringTime": 4.5}],
            ),
            FakeResponse(200, {"pathIndex": 0, "version": "1.2.3"}),
        ]
    )
    client = OtoApiClient(
        session,  # type: ignore[arg-type]
        OtoCredentials("account-id", "refresh", "id-token", 10**12),
    )
    devices = await client.async_get_devices()

    assert devices[0].watering is True
    assert devices[0].zones[0].watering_time_min == 4.5
    get_requests = [request for request in session.requests if request["method"] == "GET"]
    assert get_requests
    assert all("Content-Type" not in request.get("headers", {}) for request in get_requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [{}, {"pathIndex": "0"}, {"pathIndex": -1}])
async def test_invalid_status_is_not_treated_as_idle(status: dict[str, Any]) -> None:
    session = FakeSession(
        [
            FakeResponse(200, [{"unitName": "device-1"}]),
            FakeResponse(200, []),
            FakeResponse(200, status),
        ]
    )
    client = OtoApiClient(
        session,  # type: ignore[arg-type]
        OtoCredentials("account-id", "refresh", "id-token", 10**12),
    )
    with pytest.raises(OtoResponseError, match="status response was invalid"):
        await client.async_get_devices()


@pytest.mark.asyncio
async def test_start_uses_depth_and_never_retries() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "scheduleId": "schedule-1",
                    "schedule_item": {"runtime_min": 2.5},
                },
            )
        ]
    )
    client = OtoApiClient(
        session,  # type: ignore[arg-type]
        OtoCredentials("account-id", "refresh", "id-token", 10**12),
    )
    result = await client.async_start_zone("device-1", "zone-1", 1.0)

    assert result.runtime_min == 2.5
    assert len(session.requests) == 1
    request = session.requests[0]
    assert request["method"] == "POST"
    assert request["url"] == (
        f"{EMS}/account/account-id/routines/executions"
        "?allow_conflicts=true&overwrite_conflicts=false"
    )
    assert request["json"] == {
        "deviceId": "device-1",
        "zoneId": "zone-1",
        "wateringQuantity": 1.0,
    }
    assert request["headers"] == {"Authorization": "Bearer id-token"}
    assert result.schedule_id == "schedule-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"message": "ok"}, {"scheduleId": ""}, "OK"])
async def test_start_without_schedule_id_is_an_error(payload: Any) -> None:
    session = FakeSession([FakeResponse(200, payload)])
    client = OtoApiClient(
        session,  # type: ignore[arg-type]
        OtoCredentials("account-id", "refresh", "id-token", 10**12),
    )
    with pytest.raises(OtoResponseError, match="did not schedule"):
        await client.async_start_zone("device-1", "zone-1", 1.0)
    assert len(session.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", [0.9, 50.1, float("inf"), float("nan")])
async def test_start_rejects_unsafe_depth(depth: float) -> None:
    session = FakeSession([])
    client = OtoApiClient(
        session,  # type: ignore[arg-type]
        OtoCredentials("account-id", "refresh", "id-token", 10**12),
    )
    with pytest.raises(ValueError, match="between 1 and 50"):
        await client.async_start_zone("device-1", "zone-1", depth)
    assert session.requests == []


@pytest.mark.asyncio
async def test_refresh_token_rotation_callback() -> None:
    updates: list[OtoCredentials] = []

    async def capture(credentials: OtoCredentials) -> None:
        updates.append(credentials)

    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "id_token": "new-id",
                    "refresh_token": "new-refresh",
                    "expires_in": "3600",
                    "user_id": "account-id",
                },
            )
        ]
    )
    client = OtoApiClient(
        session,  # type: ignore[arg-type]
        OtoCredentials("account-id", "old-refresh"),
        capture,
    )
    await client.async_refresh_token()

    assert updates[0].refresh_token == "new-refresh"
