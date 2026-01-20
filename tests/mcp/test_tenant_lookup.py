"""Tests for tenant resolution helpers."""

from __future__ import annotations

from typing import Any, cast

import asyncpg
import pytest

from src.mcp.utils.tenant_lookup import resolve_tenant_to_workos_org


class _FakeConn:
    def __init__(self, row: Any) -> None:
        self._row = row

    async def fetchrow(
        self, query: str, tenant_id: str
    ) -> Any:  # pragma: no cover - executed in tests
        return self._row


class _AcquireCM:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakePool:
    def __init__(self, row: Any) -> None:
        self._conn = _FakeConn(row)

    def acquire(self) -> _AcquireCM:
        return _AcquireCM(self._conn)


@pytest.mark.asyncio
async def test_resolve_tenant_to_workos_org_success():
    pool = cast(asyncpg.Pool, _FakePool({"workos_org_id": "org_123"}))
    org_id = await resolve_tenant_to_workos_org("tn_abc", control_pool=pool)
    assert org_id == "org_123"


@pytest.mark.asyncio
async def test_resolve_tenant_to_workos_org_missing():
    pool = cast(asyncpg.Pool, _FakePool(None))
    org_id = await resolve_tenant_to_workos_org("tn_missing", control_pool=pool)
    assert org_id is None


@pytest.mark.asyncio
async def test_resolve_tenant_missing_argument():
    with pytest.raises(ValueError):
        await resolve_tenant_to_workos_org(
            "",
            control_pool=cast(asyncpg.Pool, _FakePool(None)),
        )
