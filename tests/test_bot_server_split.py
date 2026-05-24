from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytest


@dataclass
class DummyUser:
    id: int = 123


class DummyMessage:
    def __init__(self, text: str, dt: datetime):
        self.text = text
        self.date = dt
        self.replies: list[str] = []

    async def reply_text(self, text: str):
        self.replies.append(text)


@dataclass
class DummyUpdate:
    message: DummyMessage
    effective_user: DummyUser = field(default_factory=DummyUser)


@pytest.fixture
def bot_server_module(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("RECEIVER_URL", "http://example.invalid")
    monkeypatch.setenv("RECEIVER_SECRET", "s" * 32)
    monkeypatch.setenv("ALLOWED_USER_IDS", "")

    import bot_server

    return importlib.reload(bot_server)


def _make_update() -> DummyUpdate:
    msg = DummyMessage("Еда; Лента; 1755.5\nЗарплата; Работа; +1000", datetime(2026, 5, 6, 14, 27, tzinfo=timezone.utc))
    return DummyUpdate(message=msg)


def test_handle_message_retries_with_fresh_nonce_and_connection_close(bot_server_module, monkeypatch):
    update = _make_update()
    captured: list[dict[str, object]] = []
    request = httpx.Request("POST", "http://example.invalid/")
    failures = [
        httpx.ConnectError("boom-1", request=request),
        httpx.ConnectError("boom-2", request=request),
    ]

    class FakeResponse:
        def __init__(self):
            self.request = request
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"count": 2, "file": "06.05.2026.md"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content=None, headers=None):
            captured.append({"url": url, "content": content, "headers": headers, "kwargs": self.kwargs})
            if failures:
                raise failures.pop(0)
            return FakeResponse()

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(bot_server_module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot_server_module.asyncio, "sleep", fake_sleep)

    import asyncio

    asyncio.run(bot_server_module.handle_message(update, object()))

    assert update.message.replies == ["Added 2 records to 06.05.2026.md"]
    assert len(captured) == 3
    assert all(item["headers"]["Connection"] == "close" for item in captured)
    nonces = [json.loads(item["content"].decode("utf-8"))["nonce"] for item in captured]
    assert len(set(nonces)) == 3
    assert sleeps == [2.0, 4.0]
    assert captured[0]["kwargs"]["limits"].max_keepalive_connections == 0
    assert captured[0]["kwargs"]["timeout"].connect == 10.0


def test_handle_message_returns_error_once_http_status_reaches_receiver(bot_server_module, monkeypatch):
    update = _make_update()
    captured: list[dict[str, object]] = []
    response = httpx.Response(403, request=httpx.Request("POST", "http://example.invalid/"), content=b"Forbidden")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content=None, headers=None):
            captured.append({"url": url, "content": content, "headers": headers})
            return response

    monkeypatch.setattr(bot_server_module.httpx, "AsyncClient", FakeClient)
    import asyncio

    asyncio.run(bot_server_module.handle_message(update, object()))

    assert len(captured) == 1
    assert len(update.message.replies) == 1
    assert update.message.replies[0].startswith("Ошибка связи с ПК:")


def test_handle_message_returns_error_after_all_network_retries(bot_server_module, monkeypatch):
    update = _make_update()
    request = httpx.Request("POST", "http://example.invalid/")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content=None, headers=None):
            raise httpx.ConnectError("All connection attempts failed", request=request)

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(bot_server_module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot_server_module.asyncio, "sleep", fake_sleep)

    import asyncio

    asyncio.run(bot_server_module.handle_message(update, object()))

    assert len(update.message.replies) == 1
    assert "All connection attempts failed" in update.message.replies[0]
    assert sleeps == [
        bot_server_module._receiver_retry_delay_sec(i)
        for i in range(bot_server_module._RECEIVER_MAX_ATTEMPTS - 1)
    ]
