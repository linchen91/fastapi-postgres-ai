import asyncio

import httpx
import pytest
from fastapi import HTTPException

import routers.ai_summary as mod


def _configure(monkeypatch):
    monkeypatch.setattr(mod, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(mod, "OPENROUTER_URL", "https://openrouter.test/api/v1")
    monkeypatch.setattr(mod, "OPENROUTER_MODEL", "test-model")


def _patch_sleep(monkeypatch):
    slept = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return slept


def _patch_client(monkeypatch, responses):
    client = FakeAsyncClient(responses)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    return client


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("not json")
        return self._json_data


class FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        response = self._responses[self.calls]
        self.calls += 1
        return response


def test_error_detail_includes_message():
    r = FakeResponse(429, {"error": {"message": "rate-limited upstream"}})
    detail = mod._openrouter_error_detail(r)
    assert detail == "OpenRouter API error (HTTP 429): rate-limited upstream"


def test_error_detail_non_json_body():
    r = FakeResponse(502)
    detail = mod._openrouter_error_detail(r)
    assert detail == "OpenRouter API error (HTTP 502)."


def test_error_detail_json_without_error_key():
    r = FakeResponse(400, {"foo": "bar"})
    detail = mod._openrouter_error_detail(r)
    assert detail == "OpenRouter API error (HTTP 400)."


def test_summary_success(monkeypatch):
    _configure(monkeypatch)
    client = _patch_client(monkeypatch, [
        FakeResponse(200, {"choices": [{"message": {"content": "all good"}}]}),
    ])
    result = asyncio.run(mod.ai_summary({"stats": {"deviceCount": 1}}))
    assert result == {"summary": "all good"}
    assert client.calls == 1


def test_summary_retries_on_429_then_succeeds(monkeypatch):
    _configure(monkeypatch)
    slept = _patch_sleep(monkeypatch)
    client = _patch_client(monkeypatch, [
        FakeResponse(429, {"error": {"message": "temporarily rate-limited"}}),
        FakeResponse(200, {"choices": [{"message": {"content": "recovered"}}]}),
    ])
    result = asyncio.run(mod.ai_summary({"stats": {"deviceCount": 1}}))
    assert result == {"summary": "recovered"}
    assert client.calls == 2
    assert slept == [2]


def test_summary_fails_after_max_attempts(monkeypatch):
    _configure(monkeypatch)
    slept = _patch_sleep(monkeypatch)
    client = _patch_client(monkeypatch, [
        FakeResponse(429, {"error": {"message": "rate-limited upstream"}}),
        FakeResponse(429, {"error": {"message": "rate-limited upstream"}}),
        FakeResponse(429, {"error": {"message": "rate-limited upstream"}}),
    ])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.ai_summary({"stats": {"deviceCount": 1}}))
    assert exc.value.status_code == 429
    assert "rate-limited upstream" in exc.value.detail
    assert client.calls == 3
    assert slept == [2, 4]


def test_summary_non_retryable_status_fails_immediately(monkeypatch):
    _configure(monkeypatch)
    slept = _patch_sleep(monkeypatch)
    client = _patch_client(monkeypatch, [
        FakeResponse(400, {"error": {"message": "model not found"}}),
    ])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.ai_summary({"stats": {"deviceCount": 1}}))
    assert exc.value.status_code == 400
    assert "model not found" in exc.value.detail
    assert client.calls == 1
    assert slept == []


def test_summary_missing_stats(monkeypatch):
    _configure(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.ai_summary({}))
    assert exc.value.status_code == 400


def test_summary_missing_config(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(mod, "OPENROUTER_API_KEY", None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mod.ai_summary({"stats": {"deviceCount": 1}}))
    assert exc.value.status_code == 500
