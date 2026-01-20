"""Tests for WorkOS user upsert helper."""

from __future__ import annotations

import httpx
import pytest

from src.mcp.utils.workos_user import WorkOSUserUpsertResult, upsert_workos_user


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            raise RuntimeError("No mock responses left")
        return self._responses.pop(0)


def _client_from_responses(
    responses: list[httpx.Response],
) -> tuple[httpx.AsyncClient, _MockTransport]:
    transport = _MockTransport(responses)
    client = httpx.AsyncClient(
        transport=transport, base_url="https://api.workos.com/user_management"
    )
    return client, transport


@pytest.mark.asyncio
async def test_upsert_workos_user_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKOS_API_KEY", "key")

    responses = [
        httpx.Response(200, json={"data": [{"id": "user_1", "email": "user@example.com"}]}),
        httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "mem_1",
                        "user_id": "user_1",
                        "organization_id": "org_1",
                        "status": "active",
                    }
                ]
            },
        ),
    ]

    client, _ = _client_from_responses(responses)

    try:
        result = await upsert_workos_user(
            email="user@example.com", organization_id="org_1", client=client
        )
        assert result == WorkOSUserUpsertResult(
            success=True, user_id="user_1", email="user@example.com", created=False, assigned=True
        )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_upsert_creates_user_and_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKOS_API_KEY", "key")

    responses = [
        httpx.Response(200, json={"data": []}),
        httpx.Response(201, json={"id": "user_2", "email": "user@example.com"}),
        httpx.Response(200, json={"data": []}),
        httpx.Response(201, json={"id": "mem_2"}),
    ]
    client, _ = _client_from_responses(responses)

    try:
        result = await upsert_workos_user(
            email="user@example.com", organization_id="org_1", client=client
        )
        assert result.success is True
        assert result.user_id == "user_2"
        assert result.created is True
        assert result.assigned is True
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_upsert_fails_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKOS_API_KEY", raising=False)
    result = await upsert_workos_user(email="user@example.com", organization_id="org_1")
    assert result.success is False
    assert "WORKOS_API_KEY" in (result.error or "")


@pytest.mark.asyncio
async def test_upsert_handles_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKOS_API_KEY", "key")
    responses = [httpx.Response(500, json={"error": "boom"})]
    client, _ = _client_from_responses(responses)

    try:
        result = await upsert_workos_user(
            email="user@example.com", organization_id="org_1", client=client
        )
        assert result.success is False
        assert "500" in (result.error or "")
    finally:
        await client.aclose()
