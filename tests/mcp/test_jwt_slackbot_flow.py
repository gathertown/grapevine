"""Test that internal JWT-authenticated requests still resolve tenant context."""

from __future__ import annotations

import base64
import json
from typing import Any, cast

import pytest
from fastmcp.server.context import Context
from fastmcp.server.middleware import MiddlewareContext

from src.mcp.middleware.org_context import OrgContextMiddleware


class SimpleAccessToken:
    def __init__(self, token: str) -> None:
        self.token = token


class SimpleUser:
    def __init__(self, token: str) -> None:
        self.access_token = SimpleAccessToken(token)


class DummyRequest:
    def __init__(self, token: str) -> None:
        self.user = SimpleUser(token)


@pytest.mark.asyncio
async def test_jwt_flow_sets_tenant_context(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = base64.urlsafe_b64encode(json.dumps({"tenant_id": "tn_jwt_123"}).encode()).rstrip(
        b"="
    )
    token = f"header.{payload.decode()}.sig"

    request = DummyRequest(token)
    monkeypatch.setattr("src.mcp.middleware.org_context.get_http_request", lambda: request)

    middleware = OrgContextMiddleware()
    state: dict[str, Any] = {}

    class DummyContext:
        def set_state(self, key: str, value: Any) -> None:
            state[key] = value

        def get_state(self, key: str) -> Any:
            return state.get(key)

    dummy_context = DummyContext()
    middleware_context = MiddlewareContext(
        message=None,
        fastmcp_context=cast(Context, dummy_context),
    )

    async def call_next(ctx: MiddlewareContext[Any]) -> str:
        return "ok"

    result = await middleware.on_call_tool(middleware_context, cast(Any, call_next))

    assert result == "ok"
    assert state.get("tenant_id") == "tn_jwt_123"
