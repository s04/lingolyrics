import os

os.environ["LINGOLYRICS_LOAD_ENV"] = "0"

import pytest

import cache_service


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_service, "CACHE_DIR", tmp_path / "cache")
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "LYRICFETCH_BINARY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    import httpx
    import requests

    def blocked(*args, **kwargs):
        raise AssertionError("Live network access is disabled in tests; mock the provider.")

    async def blocked_async(*args, **kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked_async)
    monkeypatch.setattr(requests.Session, "request", blocked)
