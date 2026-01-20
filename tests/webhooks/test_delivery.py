from typing import Any

import pytest

from src.webhooks.delivery import WebhookSubscription, send_single_webhook


class DummyResponse:
    """Simple stand-in for httpx.Response with configurable status code."""

    def __init__(self, status_code: int):
        self.status_code = status_code


@pytest.mark.asyncio
async def test_send_single_webhook_success(monkeypatch):
    calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            calls.append((url, json, headers))
            return DummyResponse(200)

    monkeypatch.setattr("src.webhooks.delivery.httpx.AsyncClient", DummyClient)

    subscription = WebhookSubscription("sub-1", "https://example.com/webhook", "secret")
    payload = {
        "tenant_id": "tenant-123",
        "data": {"document_id": "doc-456", "source": "github"},
    }

    await send_single_webhook(
        subscription,
        payload,
        max_attempts=3,
        base_backoff_seconds=0.0,
    )

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_send_single_webhook_retries_with_backoff(monkeypatch):
    calls: list[int] = []
    sleep_calls: list[float] = []
    responses = [DummyResponse(500), DummyResponse(500), DummyResponse(500)]

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            calls.append(1)
            return responses.pop(0)

    async def fake_sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr("src.webhooks.delivery.httpx.AsyncClient", DummyClient)
    monkeypatch.setattr("src.webhooks.delivery.asyncio.sleep", fake_sleep)

    subscription = WebhookSubscription("sub-2", "https://example.com/webhook", "secret")
    payload = {
        "tenant_id": "tenant-123",
        "data": {"document_id": "doc-456", "source": "github"},
    }

    await send_single_webhook(
        subscription,
        payload,
        max_attempts=3,
        base_backoff_seconds=1.0,
        max_backoff_seconds=5.0,
    )

    assert len(calls) == 3
    assert sleep_calls == [1.0, 2.0]
    assert responses == []
